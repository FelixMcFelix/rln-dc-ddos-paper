/*
 * Copyright (c) 2015, 2016 VMware, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at:
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "Conntrack.h"
#include "IpFragment.h"
#include "Jhash.h"
#include "PacketParser.h"
#include "Event.h"
#include "Conntrack-nat.h"

#pragma warning(push)
#pragma warning(disable:4311)

#define WINDOWS_TICK 10000000
#define SEC_TO_UNIX_EPOCH 11644473600LL
#define SEC_TO_NANOSEC 1000000000LL

KSTART_ROUTINE OvsConntrackEntryCleaner;
static PLIST_ENTRY ovsConntrackTable;
static OVS_CT_THREAD_CTX ctThreadCtx;
static PNDIS_RW_LOCK_EX ovsConntrackLockObj;
extern POVS_SWITCH_CONTEXT gOvsSwitchContext;
static UINT64 ctTotalEntries;

static __inline NDIS_STATUS OvsCtFlush(UINT16 zone);

/*
 *----------------------------------------------------------------------------
 * OvsInitConntrack
 *     Initialize the components used by Connection Tracking
 *----------------------------------------------------------------------------
 */
NTSTATUS
OvsInitConntrack(POVS_SWITCH_CONTEXT context)
{
    NTSTATUS status;
    HANDLE threadHandle = NULL;
    ctTotalEntries = 0;

    /* Init the sync-lock */
    ovsConntrackLockObj = NdisAllocateRWLock(context->NdisFilterHandle);
    if (ovsConntrackLockObj == NULL) {
        return STATUS_INSUFFICIENT_RESOURCES;
    }

    /* Init the Hash Buffer */
    ovsConntrackTable = OvsAllocateMemoryWithTag(sizeof(LIST_ENTRY)
                                                 * CT_HASH_TABLE_SIZE,
                                                 OVS_CT_POOL_TAG);
    if (ovsConntrackTable == NULL) {
        NdisFreeRWLock(ovsConntrackLockObj);
        ovsConntrackLockObj = NULL;
        return STATUS_INSUFFICIENT_RESOURCES;
    }

    for (int i = 0; i < CT_HASH_TABLE_SIZE; i++) {
        InitializeListHead(&ovsConntrackTable[i]);
    }

    /* Init CT Cleaner Thread */
    KeInitializeEvent(&ctThreadCtx.event, NotificationEvent, FALSE);
    status = PsCreateSystemThread(&threadHandle, SYNCHRONIZE, NULL, NULL,
                                  NULL, OvsConntrackEntryCleaner,
                                  &ctThreadCtx);

    if (status != STATUS_SUCCESS) {
        NdisFreeRWLock(ovsConntrackLockObj);
        ovsConntrackLockObj = NULL;

        OvsFreeMemoryWithTag(ovsConntrackTable, OVS_CT_POOL_TAG);
        ovsConntrackTable = NULL;

        return status;
    }

    ObReferenceObjectByHandle(threadHandle, SYNCHRONIZE, NULL, KernelMode,
                              &ctThreadCtx.threadObject, NULL);
    ZwClose(threadHandle);
    threadHandle = NULL;

    status = OvsNatInit();

    if (status != STATUS_SUCCESS) {
        OvsCleanupConntrack();
        return status;
    }
    return STATUS_SUCCESS;
}

/*
 *----------------------------------------------------------------------------
 * OvsCleanupConntrack
 *     Cleanup memory and thread that were spawned for Connection tracking
 *----------------------------------------------------------------------------
 */
VOID
OvsCleanupConntrack(VOID)
{
    LOCK_STATE_EX lockState;
    NdisAcquireRWLockWrite(ovsConntrackLockObj, &lockState, 0);
    ctThreadCtx.exit = 1;
    KeSetEvent(&ctThreadCtx.event, 0, FALSE);
    NdisReleaseRWLock(ovsConntrackLockObj, &lockState);

    KeWaitForSingleObject(ctThreadCtx.threadObject, Executive,
                          KernelMode, FALSE, NULL);
    ObDereferenceObject(ctThreadCtx.threadObject);

    /* Force flush all entries before removing */
    OvsCtFlush(0);

    if (ovsConntrackTable) {
        OvsFreeMemoryWithTag(ovsConntrackTable, OVS_CT_POOL_TAG);
        ovsConntrackTable = NULL;
    }

    NdisFreeRWLock(ovsConntrackLockObj);
    ovsConntrackLockObj = NULL;
    OvsNatCleanup();
}

static __inline VOID
OvsCtKeyReverse(OVS_CT_KEY *key)
{
    struct ct_endpoint tmp;
    tmp = key->src;
    key->src = key->dst;
    key->dst = tmp;
}

static __inline VOID
OvsCtUpdateFlowKey(struct OvsFlowKey *key,
                   UINT32 state,
                   UINT16 zone,
                   UINT32 mark,
                   struct ovs_key_ct_labels *labels)
{
    key->ct.state = state | OVS_CS_F_TRACKED;
    key->ct.zone = zone;
    key->ct.mark = mark;
    if (labels) {
        NdisMoveMemory(&key->ct.labels, labels,
                       sizeof(struct ovs_key_ct_labels));
    } else {
        memset(&key->ct.labels, 0,
               sizeof(struct ovs_key_ct_labels));
    }
}

static __inline VOID
OvsPostCtEventEntry(POVS_CT_ENTRY entry, UINT8 type)
{
    OVS_CT_EVENT_ENTRY ctEventEntry = {0};
    NdisMoveMemory(&ctEventEntry.entry, entry, sizeof(OVS_CT_ENTRY));
    ctEventEntry.type = type;
    OvsPostCtEvent(&ctEventEntry);
}

static __inline VOID
OvsCtIncrementCounters(POVS_CT_ENTRY entry, BOOLEAN reply, PNET_BUFFER_LIST nbl)
{
    if (reply) {
        entry->rev_key.byteCount+= OvsPacketLenNBL(nbl);
        entry->rev_key.packetCount++;
    } else {
        entry->key.byteCount += OvsPacketLenNBL(nbl);
        entry->key.packetCount++;
    }
}

static __inline BOOLEAN
OvsCtAddEntry(POVS_CT_ENTRY entry, OvsConntrackKeyLookupCtx *ctx,
              PNAT_ACTION_INFO natInfo, UINT64 now)
{
    NdisMoveMemory(&entry->key, &ctx->key, sizeof(OVS_CT_KEY));
    NdisMoveMemory(&entry->rev_key, &ctx->key, sizeof(OVS_CT_KEY));
    OvsCtKeyReverse(&entry->rev_key);

    /* NatInfo is always initialized to be disabled, so that if NAT action
     * fails, we will not end up deleting an non-existent NAT entry.
     */
    if (natInfo == NULL) {
        entry->natInfo.natAction = NAT_ACTION_NONE;
    } else {
        if (OvsIsForwardNat(natInfo->natAction)) {
            entry->natInfo = *natInfo;
            if (!OvsNatTranslateCtEntry(entry)) {
                return FALSE;
            }
            ctx->hash = OvsHashCtKey(&entry->key);
        } else {
            entry->natInfo.natAction = natInfo->natAction;
        }
    }

    entry->timestampStart = now;
    InsertHeadList(&ovsConntrackTable[ctx->hash & CT_HASH_TABLE_MASK],
                   &entry->link);

    ctTotalEntries++;
    return TRUE;
}

static __inline POVS_CT_ENTRY
OvsCtEntryCreate(OvsForwardingContext *fwdCtx,
                 UINT8 ipProto,
                 UINT32 l4Offset,
                 OvsConntrackKeyLookupCtx *ctx,
                 OvsFlowKey *key,
                 PNAT_ACTION_INFO natInfo,
                 BOOLEAN commit,
                 UINT64 currentTime,
                 BOOLEAN *entryCreated)
{
    POVS_CT_ENTRY entry = NULL;
    UINT32 state = 0;
    POVS_CT_ENTRY parentEntry;
    PNET_BUFFER_LIST curNbl = fwdCtx->curNbl;

    *entryCreated = FALSE;
    state |= OVS_CS_F_NEW;

    parentEntry = OvsCtRelatedLookup(ctx->key, currentTime);
    if (parentEntry != NULL) {
        state |= OVS_CS_F_RELATED;
    }

    switch (ipProto) {
    case IPPROTO_TCP:
    {
        TCPHdr tcpStorage;
        const TCPHdr *tcp;
        tcp = OvsGetTcp(curNbl, l4Offset, &tcpStorage);
        if (!OvsConntrackValidateTcpPacket(tcp)) {
            state = OVS_CS_F_INVALID;
            break;
        }

        if (commit) {
            entry = OvsConntrackCreateTcpEntry(tcp, curNbl, currentTime);
        }
        break;
    }
    case IPPROTO_ICMP:
    {
        ICMPHdr storage;
        const ICMPHdr *icmp;
        icmp = OvsGetIcmp(curNbl, l4Offset, &storage);
        if (!OvsConntrackValidateIcmpPacket(icmp)) {
            state = OVS_CS_F_INVALID;
            break;
        }

        if (commit) {
            entry = OvsConntrackCreateIcmpEntry(currentTime);
        }
        break;
    }
    case IPPROTO_UDP:
    {
        if (commit) {
            entry = OvsConntrackCreateOtherEntry(currentTime);
        }
        break;
    }
    default:
        state = OVS_CS_F_INVALID;
        break;
    }

    if (state != OVS_CS_F_INVALID && commit) {
        if (entry) {
            entry->parent = parentEntry;
            if (OvsCtAddEntry(entry, ctx, natInfo, currentTime)) {
                *entryCreated = TRUE;
            } else {
                /* Unable to add entry to the list */
                OvsFreeMemoryWithTag(entry, OVS_CT_POOL_TAG);
                state = OVS_CS_F_INVALID;
                entry = NULL;
            }
        } else {
            /* OvsAllocateMemoryWithTag returned NULL; treat as invalid */
            state = OVS_CS_F_INVALID;
        }
    }

    OvsCtUpdateFlowKey(key, state, ctx->key.zone, 0, NULL);
    if (entry) {
        OvsCtIncrementCounters(entry, ctx->reply, curNbl);
    }
    return entry;
}

static enum CT_UPDATE_RES
OvsCtUpdateEntry(OVS_CT_ENTRY* entry,
                 PNET_BUFFER_LIST nbl,
                 UINT8 ipProto,
                 UINT32 l4Offset,
                 BOOLEAN reply,
                 UINT64 now)
{
    switch (ipProto) {
    case IPPROTO_TCP:
    {
        TCPHdr tcpStorage;
        const TCPHdr *tcp;
        tcp = OvsGetTcp(nbl, l4Offset, &tcpStorage);
        if (!tcp) {
            return CT_UPDATE_INVALID;
        }
        return OvsConntrackUpdateTcpEntry(entry, tcp, nbl, reply, now);
    }
    case IPPROTO_ICMP:
        return OvsConntrackUpdateIcmpEntry(entry, reply, now);
    case IPPROTO_UDP:
        return OvsConntrackUpdateOtherEntry(entry, reply, now);
    default:
        return CT_UPDATE_INVALID;
    }
}

static __inline VOID
OvsCtEntryDelete(POVS_CT_ENTRY entry)
{
    if (entry == NULL) {
        return;
    }
    if (entry->natInfo.natAction) {
        OvsNatDeleteKey(&entry->key);
    }
    OvsPostCtEventEntry(entry, OVS_EVENT_CT_DELETE);
    RemoveEntryList(&entry->link);
    OvsFreeMemoryWithTag(entry, OVS_CT_POOL_TAG);
    ctTotalEntries--;
}

static __inline BOOLEAN
OvsCtEntryExpired(POVS_CT_ENTRY entry)
{
    UINT64 currentTime;
    NdisGetCurrentSystemTime((LARGE_INTEGER *)&currentTime);
    return entry->expiration < currentTime;
}

static __inline NDIS_STATUS
OvsDetectCtPacket(OvsForwardingContext *fwdCtx,
                  OvsFlowKey *key,
                  PNET_BUFFER_LIST *newNbl)
{
    /* Currently we support only Unfragmented TCP packets */
    switch (ntohs(key->l2.dlType)) {
    case ETH_TYPE_IPV4:
        if (key->ipKey.nwFrag != OVS_FRAG_TYPE_NONE) {
            return OvsProcessIpv4Fragment(fwdCtx->switchContext,
                                          &fwdCtx->curNbl,
                                          fwdCtx->completionList,
                                          fwdCtx->fwdDetail->SourcePortId,
                                          key->tunKey.tunnelId,
                                          newNbl);
        }
        if (key->ipKey.nwProto == IPPROTO_TCP
            || key->ipKey.nwProto == IPPROTO_UDP
            || key->ipKey.nwProto == IPPROTO_ICMP) {
            return NDIS_STATUS_SUCCESS;
        }
        return NDIS_STATUS_NOT_SUPPORTED;
    case ETH_TYPE_IPV6:
        return NDIS_STATUS_NOT_SUPPORTED;
    }

    return NDIS_STATUS_NOT_SUPPORTED;
}

BOOLEAN
OvsCtKeyAreSame(OVS_CT_KEY ctxKey, OVS_CT_KEY entryKey)
{
    return ((NdisEqualMemory(&ctxKey.src, &entryKey.src,
                             sizeof(struct ct_endpoint))) &&
            (NdisEqualMemory(&ctxKey.dst, &entryKey.dst,
                             sizeof(struct ct_endpoint))) &&
            (ctxKey.dl_type == entryKey.dl_type) &&
            (ctxKey.nw_proto == entryKey.nw_proto) &&
            (ctxKey.zone == entryKey.zone));
}

POVS_CT_ENTRY
OvsCtLookup(OvsConntrackKeyLookupCtx *ctx)
{
    PLIST_ENTRY link;
    POVS_CT_ENTRY entry;
    BOOLEAN reply = FALSE;
    POVS_CT_ENTRY found = NULL;

    /* Reverse NAT must be performed before OvsCtLookup, so here
     * we simply need to flip the src and dst in key and compare
     * they are equal. Note that flipped key is not equal to
     * rev_key due to NAT effect.
     */
    OVS_CT_KEY revCtxKey = ctx->key;
    OvsCtKeyReverse(&revCtxKey);

    if (!ctTotalEntries) {
        return found;
    }

    LIST_FORALL(&ovsConntrackTable[ctx->hash & CT_HASH_TABLE_MASK], link) {
        entry = CONTAINING_RECORD(link, OVS_CT_ENTRY, link);

        if (OvsCtKeyAreSame(ctx->key, entry->key)) {
            found = entry;
            reply = FALSE;
            break;
        }

        if (OvsCtKeyAreSame(revCtxKey, entry->key)) {
            found = entry;
            reply = TRUE;
            break;
        }
    }

    if (found) {
        if (OvsCtEntryExpired(found)) {
            found = NULL;
        } else {
            ctx->reply = reply;
        }
    }

    ctx->entry = found;
    return found;
}

UINT32
OvsHashCtKey(const OVS_CT_KEY *key)
{
    UINT32 hsrc, hdst, hash;
    hsrc = OvsJhashBytes((UINT32*) &key->src, sizeof(key->src), 0);
    hdst = OvsJhashBytes((UINT32*) &key->dst, sizeof(key->dst), 0);
    hash = hsrc ^ hdst; /* TO identify reverse traffic */
    hash = OvsJhashBytes((uint32_t *) &key->dst + 1,
                         ((uint32_t *) (key + 1) -
                         (uint32_t *) (&key->dst + 1)),
                         hash);
    return hash;
}

static UINT8
OvsReverseIcmpType(UINT8 type)
{
    switch (type) {
    case ICMP4_ECHO_REQUEST:
        return ICMP4_ECHO_REPLY;
    case ICMP4_ECHO_REPLY:
        return ICMP4_ECHO_REQUEST;
    case ICMP4_TIMESTAMP_REQUEST:
        return ICMP4_TIMESTAMP_REPLY;
    case ICMP4_TIMESTAMP_REPLY:
        return ICMP4_TIMESTAMP_REQUEST;
    case ICMP4_INFO_REQUEST:
        return ICMP4_INFO_REPLY;
    case ICMP4_INFO_REPLY:
        return ICMP4_INFO_REQUEST;
    default:
        return 0;
    }
}

static __inline NDIS_STATUS
OvsCtSetupLookupCtx(OvsFlowKey *flowKey,
                    UINT16 zone,
                    OvsConntrackKeyLookupCtx *ctx,
                    PNET_BUFFER_LIST curNbl,
                    UINT32 l4Offset)
{
    const OVS_NAT_ENTRY *natEntry;
    ctx->key.zone = zone;
    ctx->key.dl_type = flowKey->l2.dlType;
    ctx->related = FALSE;

    /* Extract L3 and L4*/
    if (flowKey->l2.dlType == htons(ETH_TYPE_IPV4)) {
        ctx->key.src.addr.ipv4 = flowKey->ipKey.nwSrc;
        ctx->key.dst.addr.ipv4 = flowKey->ipKey.nwDst;
        ctx->key.nw_proto = flowKey->ipKey.nwProto;

        ctx->key.src.port = flowKey->ipKey.l4.tpSrc;
        ctx->key.dst.port = flowKey->ipKey.l4.tpDst;
        if (flowKey->ipKey.nwProto == IPPROTO_ICMP) {
            ICMPHdr icmpStorage;
            const ICMPHdr *icmp;
            icmp = OvsGetIcmp(curNbl, l4Offset, &icmpStorage);
            ASSERT(icmp);

            /* Related bit is set when ICMP has an error */
            /* XXX parse out the appropriate src and dst from inner pkt */
            switch (icmp->type) {
            case ICMP4_ECHO_REQUEST:
            case ICMP4_ECHO_REPLY:
            case ICMP4_TIMESTAMP_REQUEST:
            case ICMP4_TIMESTAMP_REPLY:
            case ICMP4_INFO_REQUEST:
            case ICMP4_INFO_REPLY:
                if (icmp->code != 0) {
                    return NDIS_STATUS_INVALID_PACKET;
                }
                /* Separate ICMP connection: identified using id */
                ctx->key.dst.icmp_id = icmp->fields.echo.id;
                ctx->key.src.icmp_id = icmp->fields.echo.id;
                ctx->key.src.icmp_type = icmp->type;
                ctx->key.dst.icmp_type = OvsReverseIcmpType(icmp->type);
                break;
            case ICMP4_DEST_UNREACH:
            case ICMP4_TIME_EXCEEDED:
            case ICMP4_PARAM_PROB:
            case ICMP4_SOURCE_QUENCH:
            case ICMP4_REDIRECT: {
                /* XXX Handle inner packet */
                ctx->related = TRUE;
                break;
            }
            default:
                ctx->related = FALSE;
            }
        }
    } else if (flowKey->l2.dlType == htons(ETH_TYPE_IPV6)) {
        ctx->key.src.addr.ipv6 = flowKey->ipv6Key.ipv6Src;
        ctx->key.dst.addr.ipv6 = flowKey->ipv6Key.ipv6Dst;
        ctx->key.nw_proto = flowKey->ipv6Key.nwProto;

        ctx->key.src.port = flowKey->ipv6Key.l4.tpSrc;
        ctx->key.dst.port = flowKey->ipv6Key.l4.tpDst;
        /* XXX Handle ICMPv6 errors*/
    } else {
        return NDIS_STATUS_INVALID_PACKET;
    }

    natEntry = OvsNatLookup(&ctx->key, TRUE);
    if (natEntry) {
        /* Translate address first for reverse NAT */
        ctx->key = natEntry->ctEntry->key;
        OvsCtKeyReverse(&ctx->key);
    }

    ctx->hash = OvsHashCtKey(&ctx->key);
    return NDIS_STATUS_SUCCESS;
}

static __inline BOOLEAN
OvsDetectFtpPacket(OvsFlowKey *key) {
    return (key->ipKey.nwProto == IPPROTO_TCP &&
            (ntohs(key->ipKey.l4.tpDst) == IPPORT_FTP ||
            ntohs(key->ipKey.l4.tpSrc) == IPPORT_FTP));
}

/*
 *----------------------------------------------------------------------------
 * OvsProcessConntrackEntry
 *     Check the TCP flags and set the ct_state of the entry
 *----------------------------------------------------------------------------
 */
static __inline POVS_CT_ENTRY
OvsProcessConntrackEntry(OvsForwardingContext *fwdCtx,
                         UINT32 l4Offset,
                         OvsConntrackKeyLookupCtx *ctx,
                         OvsFlowKey *key,
                         UINT16 zone,
                         NAT_ACTION_INFO *natInfo,
                         BOOLEAN commit,
                         UINT64 currentTime,
                         BOOLEAN *entryCreated)
{
    POVS_CT_ENTRY entry = ctx->entry;
    UINT32 state = 0;
    PNET_BUFFER_LIST curNbl = fwdCtx->curNbl;
    *entryCreated = FALSE;

    /* If an entry was found, update the state based on TCP flags */
    if (ctx->related) {
        state |= OVS_CS_F_RELATED;
        if (ctx->reply) {
            state |= OVS_CS_F_REPLY_DIR;
        }
    } else {
        CT_UPDATE_RES result;
        result = OvsCtUpdateEntry(entry, curNbl, key->ipKey.nwProto,
                                  l4Offset, ctx->reply, currentTime);
        switch (result) {
        case CT_UPDATE_VALID:
            state |= OVS_CS_F_ESTABLISHED;
            if (ctx->reply) {
                state |= OVS_CS_F_REPLY_DIR;
            }
            break;
        case CT_UPDATE_INVALID:
            state |= OVS_CS_F_INVALID;
            break;
        case CT_UPDATE_NEW:
            //Delete and update the Conntrack
            OvsCtEntryDelete(ctx->entry);
            ctx->entry = NULL;
            entry = OvsCtEntryCreate(fwdCtx, key->ipKey.nwProto, l4Offset,
                                     ctx, key, natInfo, commit, currentTime,
                                     entryCreated);
            if (!entry) {
                return NULL;
            }
            break;
        }
    }

    if (key->ipKey.nwProto == IPPROTO_TCP && entry) {
        /* Update the related bit if there is a parent */
        if (entry->parent) {
            state |= OVS_CS_F_RELATED;
        } else {
            POVS_CT_ENTRY parentEntry;
            parentEntry = OvsCtRelatedLookup(ctx->key, currentTime);
            entry->parent = parentEntry;
            if (parentEntry != NULL) {
                state |= OVS_CS_F_RELATED;
            }
        }
    }

    /* Copy mark and label from entry into flowKey. If actions specify
       different mark and label, update the flowKey. */
    if (entry != NULL) {
        OvsCtUpdateFlowKey(key, state, zone, entry->mark, &entry->labels);
    } else {
        OvsCtUpdateFlowKey(key, state, zone, 0, NULL);
    }
    return entry;
}

static __inline VOID
OvsConntrackSetMark(OvsFlowKey *key,
                    POVS_CT_ENTRY entry,
                    UINT32 value,
                    UINT32 mask,
                    BOOLEAN *markChanged)
{
    UINT32 newMark;
    newMark = value | (entry->mark & ~(mask));
    if (entry->mark != newMark) {
        entry->mark = newMark;
        key->ct.mark = newMark;
        *markChanged = TRUE;
    }
}

static __inline void
OvsConntrackSetLabels(OvsFlowKey *key,
                      POVS_CT_ENTRY entry,
                      struct ovs_key_ct_labels *val,
                      struct ovs_key_ct_labels *mask,
                      BOOLEAN *labelChanged)
{
    ovs_u128 v, m, pktMdLabel = {0};
    memcpy(&v, val, sizeof v);
    memcpy(&m, mask, sizeof m);

    pktMdLabel.u64.lo = v.u64.lo | (pktMdLabel.u64.lo & ~(m.u64.lo));
    pktMdLabel.u64.hi = v.u64.hi | (pktMdLabel.u64.hi & ~(m.u64.hi));

    if (!NdisEqualMemory(&entry->labels, &pktMdLabel,
                         sizeof(struct ovs_key_ct_labels))) {
        *labelChanged = TRUE;
    }
    NdisMoveMemory(&entry->labels, &pktMdLabel,
                   sizeof(struct ovs_key_ct_labels));
    NdisMoveMemory(&key->ct.labels, &pktMdLabel,
                   sizeof(struct ovs_key_ct_labels));
}

static __inline NDIS_STATUS
OvsCtExecute_(OvsForwardingContext *fwdCtx,
              OvsFlowKey *key,
              OVS_PACKET_HDR_INFO *layers,
              BOOLEAN commit,
              BOOLEAN force,
              UINT16 zone,
              MD_MARK *mark,
              MD_LABELS *labels,
              PCHAR helper,
              PNAT_ACTION_INFO natInfo,
              BOOLEAN postUpdateEvent)
{
    NDIS_STATUS status = NDIS_STATUS_SUCCESS;
    BOOLEAN triggerUpdateEvent = FALSE;
    POVS_CT_ENTRY entry = NULL;
    PNET_BUFFER_LIST curNbl = fwdCtx->curNbl;
    OvsConntrackKeyLookupCtx ctx = { 0 };
    LOCK_STATE_EX lockState;
    UINT64 currentTime;
    NdisGetCurrentSystemTime((LARGE_INTEGER *) &currentTime);


    /* Retrieve the Conntrack Key related fields from packet */
    OvsCtSetupLookupCtx(key, zone, &ctx, curNbl, layers->l4Offset);

    NdisAcquireRWLockWrite(ovsConntrackLockObj, &lockState, 0);

    /* Lookup Conntrack entries for a matching entry */
    entry = OvsCtLookup(&ctx);
    BOOLEAN entryCreated = FALSE;

    /* Delete entry in reverse direction if 'force' is specified */
    if (entry && force && ctx.reply) {
        OvsCtEntryDelete(entry);
        entry = NULL;
    }

    if (!entry && commit && ctTotalEntries >= CT_MAX_ENTRIES) {
        /* Don't proceed with processing if the max limit has been hit.
         * This blocks only new entries from being created and doesn't
         * affect existing connections.
         */
        NdisReleaseRWLock(ovsConntrackLockObj, &lockState);
        OVS_LOG_ERROR("Conntrack Limit hit: %lu", ctTotalEntries);
        return NDIS_STATUS_RESOURCES;
    }

    /* Increment the counters soon after the lookup, since we set ct.state
     * to OVS_CS_F_TRACKED after processing the ct entry.
     */
    if (entry && (!(key->ct.state & OVS_CS_F_TRACKED))) {
        OvsCtIncrementCounters(entry, ctx.reply, curNbl);
    }

    if (!entry) {
        /* If no matching entry was found, create one and add New state */
        entry = OvsCtEntryCreate(fwdCtx, key->ipKey.nwProto,
                                 layers->l4Offset, &ctx,
                                 key, natInfo, commit, currentTime,
                                 &entryCreated);
    } else {
        /* Process the entry and update CT flags */
        entry = OvsProcessConntrackEntry(fwdCtx, layers->l4Offset, &ctx, key,
                                         zone, natInfo, commit, currentTime,
                                         &entryCreated);
    }

    /*
     * Note that natInfo is not the same as entry->natInfo here. natInfo
     * is decided by action in the openflow rule, entry->natInfo is decided
     * when the entry is created. In the reverse NAT case, natInfo is
     * NAT_ACTION_REVERSE, yet entry->natInfo is NAT_ACTION_SRC or
     * NAT_ACTION_DST without NAT_ACTION_REVERSE
     */
    if (entry && natInfo->natAction != NAT_ACTION_NONE)
    {
        OvsNatPacket(fwdCtx, entry, entry->natInfo.natAction,
                     key, ctx.reply);
    }

    if (entry && mark) {
        OvsConntrackSetMark(key, entry, mark->value, mark->mask,
                            &triggerUpdateEvent);
    }

    if (entry && labels) {
        OvsConntrackSetLabels(key, entry, &labels->value, &labels->mask,
                              &triggerUpdateEvent);
    }

    if (entry && OvsDetectFtpPacket(key)) {
        /* FTP parser will always be loaded */
        UNREFERENCED_PARAMETER(helper);

        status = OvsCtHandleFtp(curNbl, key, layers, currentTime, entry,
                                (ntohs(key->ipKey.l4.tpDst) == IPPORT_FTP));
        if (status != NDIS_STATUS_SUCCESS) {
            OVS_LOG_ERROR("Error while parsing the FTP packet");
        }
    }

    /* Add original tuple information to flow Key */
    if (entry && entry->key.dl_type == ntohs(ETH_TYPE_IPV4)) {
        OVS_CT_KEY *ctKey;
        if (entry->parent != NULL) {
            POVS_CT_ENTRY parent = entry->parent;
            ctKey = &parent->key;
        } else {
            ctKey = &entry->key;
        }

        key->ct.tuple_ipv4.ipv4_src = ctKey->src.addr.ipv4_aligned;
        key->ct.tuple_ipv4.ipv4_dst = ctKey->dst.addr.ipv4_aligned;
        key->ct.tuple_ipv4.ipv4_proto = ctKey->nw_proto;

        /* Orig tuple Port is overloaded to take in ICMP-Type & Code */
        /* This mimics the behavior in lib/conntrack.c*/
        key->ct.tuple_ipv4.src_port = ctKey->nw_proto != IPPROTO_ICMP ?
                                      ctKey->src.port :
                                      htons(ctKey->src.icmp_type);
        key->ct.tuple_ipv4.dst_port = ctKey->nw_proto != IPPROTO_ICMP ?
                                      ctKey->dst.port :
                                      htons(ctKey->src.icmp_code);
    }

    if (entryCreated && entry) {
        OvsPostCtEventEntry(entry, OVS_EVENT_CT_NEW);
    }
    if (postUpdateEvent && entry && !entryCreated && triggerUpdateEvent) {
        OvsPostCtEventEntry(entry, OVS_EVENT_CT_UPDATE);
    }

    NdisReleaseRWLock(ovsConntrackLockObj, &lockState);

    return status;
}

/*
 *---------------------------------------------------------------------------
 * OvsExecuteConntrackAction
 *     Executes Conntrack actions XXX - Add more
 *     For the Ipv4 fragments, consume the orginal fragment NBL
 *---------------------------------------------------------------------------
 */
NDIS_STATUS
OvsExecuteConntrackAction(OvsForwardingContext *fwdCtx,
                          OvsFlowKey *key,
                          const PNL_ATTR a)
{
    PNL_ATTR ctAttr;
    BOOLEAN commit = FALSE;
    BOOLEAN force = FALSE;
    BOOLEAN postUpdateEvent = FALSE;
    UINT16 zone = 0;
    UINT32 eventmask = 0;
    MD_MARK *mark = NULL;
    MD_LABELS *labels = NULL;
    PCHAR helper = NULL;
    NAT_ACTION_INFO natActionInfo;
    OVS_PACKET_HDR_INFO *layers = &fwdCtx->layers;
    PNET_BUFFER_LIST newNbl = NULL;
    NDIS_STATUS status;

    memset(&natActionInfo, 0, sizeof natActionInfo);
    status = OvsDetectCtPacket(fwdCtx, key, &newNbl);
    if (status != NDIS_STATUS_SUCCESS) {
        return status;
    }

    /* XXX Convert this to NL_ATTR_FOR_EACH */
    ctAttr = NlAttrFindNested(a, OVS_CT_ATTR_ZONE);
    if (ctAttr) {
        zone = NlAttrGetU16(ctAttr);
    }
    ctAttr = NlAttrFindNested(a, OVS_CT_ATTR_COMMIT);
    if (ctAttr) {
        commit = TRUE;
    }
    ctAttr = NlAttrFindNested(a, OVS_CT_ATTR_MARK);
    if (ctAttr) {
        mark = NlAttrGet(ctAttr);
    }
    ctAttr = NlAttrFindNested(a, OVS_CT_ATTR_LABELS);
    if (ctAttr) {
        labels = NlAttrGet(ctAttr);
    }
    natActionInfo.natAction = NAT_ACTION_NONE;
    ctAttr = NlAttrFindNested(a, OVS_CT_ATTR_NAT);
    if (ctAttr) {
        /* Pares Nested NAT attributes. */
        PNL_ATTR natAttr;
        unsigned int left;
        BOOLEAN hasMinIp = FALSE;
        BOOLEAN hasMinPort = FALSE;
        BOOLEAN hasMaxIp = FALSE;
        BOOLEAN hasMaxPort = FALSE;
        NL_NESTED_FOR_EACH_UNSAFE (natAttr, left, ctAttr) {
            enum ovs_nat_attr subtype = NlAttrType(natAttr);
            switch(subtype) {
            case OVS_NAT_ATTR_SRC:
            case OVS_NAT_ATTR_DST:
                natActionInfo.natAction |=
                    ((subtype == OVS_NAT_ATTR_SRC)
                        ? NAT_ACTION_SRC : NAT_ACTION_DST);
                break;
            case OVS_NAT_ATTR_IP_MIN:
                memcpy(&natActionInfo.minAddr,
                       NlAttrData(natAttr), NlAttrGetSize(natAttr));
                hasMinIp = TRUE;
                break;
            case OVS_NAT_ATTR_IP_MAX:
                memcpy(&natActionInfo.maxAddr,
                       NlAttrData(natAttr), NlAttrGetSize(natAttr));
                hasMaxIp = TRUE;
                break;
            case OVS_NAT_ATTR_PROTO_MIN:
                natActionInfo.minPort = NlAttrGetU16(natAttr);
                hasMinPort = TRUE;
                break;
            case OVS_NAT_ATTR_PROTO_MAX:
                natActionInfo.maxPort = NlAttrGetU16(natAttr);
                hasMaxPort = TRUE;
                break;
            case OVS_NAT_ATTR_PERSISTENT:
            case OVS_NAT_ATTR_PROTO_HASH:
            case OVS_NAT_ATTR_PROTO_RANDOM:
                break;
            }
        }
        if (natActionInfo.natAction == NAT_ACTION_NONE) {
            natActionInfo.natAction = NAT_ACTION_REVERSE;
        }
        if (hasMinIp && !hasMaxIp) {
            memcpy(&natActionInfo.maxAddr,
                   &natActionInfo.minAddr,
                   sizeof(natActionInfo.maxAddr));
        }
        if (hasMinPort && !hasMaxPort) {
            natActionInfo.maxPort = natActionInfo.minPort;
        }
        if (hasMinPort || hasMaxPort) {
            if (natActionInfo.natAction & NAT_ACTION_SRC) {
                natActionInfo.natAction |= NAT_ACTION_SRC_PORT;
            } else if (natActionInfo.natAction & NAT_ACTION_DST) {
                natActionInfo.natAction |= NAT_ACTION_DST_PORT;
            }
        }
    }
    ctAttr = NlAttrFindNested(a, OVS_CT_ATTR_HELPER);
    if (ctAttr) {
        helper = NlAttrGetString(ctAttr);
        if (helper == NULL) {
            return NDIS_STATUS_INVALID_PARAMETER;
        }
        if (strcmp("ftp", helper) != 0) {
            /* Only support FTP */
            return NDIS_STATUS_NOT_SUPPORTED;
        }
    }
    ctAttr = NlAttrFindNested(a, OVS_CT_ATTR_FORCE_COMMIT);
    if (ctAttr) {
        force = TRUE;
        /* Force implicitly means commit */
        commit = TRUE;
    }
    ctAttr = NlAttrFindNested(a, OVS_CT_ATTR_EVENTMASK);
    if (ctAttr) {
        eventmask = NlAttrGetU32(ctAttr);
        /* Only mark and label updates are supported. */
        if (eventmask & (1 << IPCT_MARK | 1 << IPCT_LABEL))
            postUpdateEvent = TRUE;
    }
    /* If newNbl is not allocated, use the current Nbl*/
    status = OvsCtExecute_(fwdCtx, key, layers,
                           commit, force, zone, mark, labels, helper, &natActionInfo,
                           postUpdateEvent);
    return status;
}

/*
 *----------------------------------------------------------------------------
 * OvsConntrackEntryCleaner
 *     Runs periodically and cleans up the connection tracker
 *----------------------------------------------------------------------------
 */
VOID
OvsConntrackEntryCleaner(PVOID data)
{

    POVS_CT_THREAD_CTX context = (POVS_CT_THREAD_CTX)data;
    PLIST_ENTRY link, next;
    POVS_CT_ENTRY entry;
    LOCK_STATE_EX lockState;
    BOOLEAN success = TRUE;

    while (success) {
        if (ovsConntrackLockObj == NULL) {
            /* Lock has been freed by 'OvsCleanupConntrack()' */
            break;
        }
        NdisAcquireRWLockWrite(ovsConntrackLockObj, &lockState, 0);
        if (context->exit) {
            NdisReleaseRWLock(ovsConntrackLockObj, &lockState);
            break;
        }

        /* Set the timeout for the thread and cleanup */
        INT64 threadSleepTimeout = -CT_CLEANUP_INTERVAL;

        if (ctTotalEntries) {
            for (int i = 0; i < CT_HASH_TABLE_SIZE; i++) {
                LIST_FORALL_SAFE(&ovsConntrackTable[i], link, next) {
                    entry = CONTAINING_RECORD(link, OVS_CT_ENTRY, link);
                    if (entry && OvsCtEntryExpired(entry)) {
                        OvsCtEntryDelete(entry);
                    }
                }
            }
        }
        NdisReleaseRWLock(ovsConntrackLockObj, &lockState);
        KeWaitForSingleObject(&context->event, Executive, KernelMode,
                              FALSE, (LARGE_INTEGER *)&threadSleepTimeout);
    }

    PsTerminateSystemThread(STATUS_SUCCESS);
}

/*
 *----------------------------------------------------------------------------
 * OvsCtFlush
 *     Flushes out all Conntrack Entries that match the given zone
 *----------------------------------------------------------------------------
 */
static __inline NDIS_STATUS
OvsCtFlush(UINT16 zone)
{
    PLIST_ENTRY link, next;
    POVS_CT_ENTRY entry;

    LOCK_STATE_EX lockState;
    NdisAcquireRWLockWrite(ovsConntrackLockObj, &lockState, 0);

    if (ctTotalEntries) {
        for (int i = 0; i < CT_HASH_TABLE_SIZE; i++) {
            LIST_FORALL_SAFE(&ovsConntrackTable[i], link, next) {
                entry = CONTAINING_RECORD(link, OVS_CT_ENTRY, link);
                /* zone is a non-zero value */
                if (!zone || zone == entry->key.zone)
                    OvsCtEntryDelete(entry);
            }
        }
    }

    OvsNatFlush(zone);
    NdisReleaseRWLock(ovsConntrackLockObj, &lockState);
    return NDIS_STATUS_SUCCESS;
}

NTSTATUS
OvsCtDeleteCmdHandler(POVS_USER_PARAMS_CONTEXT usrParamsCtx,
                      UINT32 *replyLen)
{
    POVS_MESSAGE msgIn = (POVS_MESSAGE)usrParamsCtx->inputBuffer;
    POVS_MESSAGE msgOut = (POVS_MESSAGE)usrParamsCtx->outputBuffer;
    PNL_MSG_HDR nlMsgHdr = &(msgIn->nlMsg);
    PNL_ATTR ctAttrs[__CTA_MAX];
    UINT32 attrOffset = NLMSG_HDRLEN + NF_GEN_MSG_HDRLEN + OVS_HDRLEN;
    NL_ERROR nlError = NL_ERROR_SUCCESS;
    NTSTATUS status;
    UINT16 zone = 0;
    NL_BUFFER nlBuf;
    UINT16 nlmsgType;
    PNL_MSG_HDR nlMsg;

    static const NL_POLICY ctZonePolicy[] = {
        [CTA_ZONE] = { .type = NL_A_BE16, .optional = TRUE },
    };

    if ((NlAttrParse(nlMsgHdr, attrOffset, NlNfMsgAttrsLen(nlMsgHdr),
        ctZonePolicy, ARRAY_SIZE(ctZonePolicy),
        ctAttrs, ARRAY_SIZE(ctAttrs)))
        != TRUE) {
        OVS_LOG_ERROR("Zone attr parsing failed for msg: %p", nlMsgHdr);
        status = STATUS_INVALID_PARAMETER;
        goto done;
    }

    if (ctAttrs[CTA_ZONE]) {
        zone = NlAttrGetU16(ctAttrs[CTA_ZONE]);
    }

    status = OvsCtFlush(zone);
    if (status == STATUS_SUCCESS) {
        nlmsgType = (NFNL_SUBSYS_CTNETLINK << 8 | IPCTNL_MSG_CT_DELETE);
        NlBufInit(&nlBuf,
                  usrParamsCtx->outputBuffer,
                  usrParamsCtx->outputLength);
        if (!NlFillOvsMsgForNfGenMsg(&nlBuf, nlmsgType, NLM_F_CREATE,
                                     msgIn->nlMsg.nlmsgSeq,
                                     msgIn->nlMsg.nlmsgPid,
                                     AF_UNSPEC,
                                     msgIn->nfGenMsg.version,
                                     0)) {
            status = STATUS_INVALID_PARAMETER;
        }
        nlMsg = (PNL_MSG_HDR)NlBufAt(&nlBuf, 0, 0);
        nlMsg->nlmsgLen = NlBufSize(&nlBuf);
        *replyLen = msgOut->nlMsg.nlmsgLen;
    }

done:
    nlError = NlMapStatusToNlErr(status);
    if (nlError != NL_ERROR_SUCCESS) {
        POVS_MESSAGE_ERROR msgError = (POVS_MESSAGE_ERROR)
                                       usrParamsCtx->outputBuffer;

        ASSERT(msgError);
        NlBuildErrorMsg(msgIn, msgError, nlError, replyLen);
        ASSERT(*replyLen != 0);
        status = STATUS_SUCCESS;
    }

    return status;
}

static __inline NDIS_STATUS
MapIpTupleToNl(PNL_BUFFER nlBuf, OVS_CT_KEY *key)
{
    NDIS_STATUS status = NDIS_STATUS_SUCCESS;
    UINT32 offset = 0;

    offset = NlMsgStartNested(nlBuf, CTA_TUPLE_IP);
    if (!offset) {
        return NDIS_STATUS_FAILURE;
    }

    if (key->dl_type == ntohs(ETH_TYPE_IPV4)) {
        if (!NlMsgPutTailU32(nlBuf, CTA_IP_V4_SRC, key->src.addr.ipv4)) {
            status = NDIS_STATUS_FAILURE;
            goto done;
        }
        if (!NlMsgPutTailU32(nlBuf, CTA_IP_V4_DST, key->dst.addr.ipv4)) {
            status = NDIS_STATUS_FAILURE;
            goto done;
        }
    } else if (key->dl_type == ntohs(ETH_TYPE_IPV6)) {
        if (!NlMsgPutTailUnspec(nlBuf, CTA_IP_V6_SRC,
                                (PCHAR)(&key->src.addr.ipv6),
                                sizeof(key->src.addr.ipv6))) {
            status = NDIS_STATUS_FAILURE;
            goto done;
        }
        if (!NlMsgPutTailUnspec(nlBuf, CTA_IP_V6_DST,
                                (PCHAR)(&key->dst.addr.ipv6),
                                sizeof(key->dst.addr.ipv6))) {
            status = NDIS_STATUS_FAILURE;
            goto done;
        }
    }

done:
    NlMsgEndNested(nlBuf, offset);
    return status;
}

static __inline NDIS_STATUS
MapProtoTupleToNl(PNL_BUFFER nlBuf, OVS_CT_KEY *key)
{
    NDIS_STATUS status = NDIS_STATUS_SUCCESS;
    UINT32 offset = 0;

    offset = NlMsgStartNested(nlBuf, CTA_TUPLE_PROTO);
    if (!offset) {
        return NDIS_STATUS_FAILURE;
    }

    if (!NlMsgPutTailU8(nlBuf, CTA_PROTO_NUM, key->nw_proto)) {
        status = NDIS_STATUS_FAILURE;
        goto done;
    }

    if (key->dl_type == ntohs(ETH_TYPE_IPV4)
        || key->dl_type == ntohs(ETH_TYPE_IPV6)) {
        /* ICMP and ICMPv6 Type, Code and ID are currently not tracked */
        if (key->nw_proto == IPPROTO_ICMP) {
            if (!NlMsgPutTailU16(nlBuf, CTA_PROTO_ICMP_ID,
                                 htons(key->src.icmp_id))) {
                status = NDIS_STATUS_FAILURE;
                goto done;
            }
            if (!NlMsgPutTailU8(nlBuf, CTA_PROTO_ICMP_TYPE,
                                key->src.icmp_type)) {
                status = NDIS_STATUS_FAILURE;
                goto done;
            }
            if (!NlMsgPutTailU8(nlBuf, CTA_PROTO_ICMP_CODE,
                                key->src.icmp_code)) {
                status = NDIS_STATUS_FAILURE;
                goto done;
            }
        } else if (key->nw_proto == IPPROTO_ICMPV6) {
            if (!NlMsgPutTailU16(nlBuf, CTA_PROTO_ICMPV6_ID, 0)) {
                status = NDIS_STATUS_FAILURE;
                goto done;
            }
            if (!NlMsgPutTailU8(nlBuf, CTA_PROTO_ICMPV6_TYPE, 0)) {
                status = NDIS_STATUS_FAILURE;
                goto done;
            }
            if (!NlMsgPutTailU8(nlBuf, CTA_PROTO_ICMPV6_CODE, 0)) {
                status = NDIS_STATUS_FAILURE;
                goto done;
            }
        } else if (key->nw_proto == IPPROTO_TCP
                   || key->nw_proto == IPPROTO_UDP) {
            if (!NlMsgPutTailU16(nlBuf, CTA_PROTO_SRC_PORT,
                                 key->src.port)) {
                status = NDIS_STATUS_FAILURE;
                goto done;
            }
            if (!NlMsgPutTailU16(nlBuf, CTA_PROTO_DST_PORT,
                                 key->dst.port)) {
                status = NDIS_STATUS_FAILURE;
                goto done;
            }
        }
    }

done:
    NlMsgEndNested(nlBuf, offset);
    return status;
}

static __inline NDIS_STATUS
MapCtKeyTupleToNl(PNL_BUFFER nlBuf,
                  UINT16 tupleType,
                  OVS_CT_KEY *key)
{
    NDIS_STATUS status = NDIS_STATUS_SUCCESS;
    UINT32 offset = 0;

    offset = NlMsgStartNested(nlBuf, tupleType);
    if (!offset) {
        return NDIS_STATUS_FAILURE;
    }

    status = MapIpTupleToNl(nlBuf, key);
    if (status != NDIS_STATUS_SUCCESS) {
        goto done;
    }

    status = MapProtoTupleToNl(nlBuf, key);
    if (status != NDIS_STATUS_SUCCESS) {
        goto done;
    }

done:
    NlMsgEndNested(nlBuf, offset);
    return status;
}

static __inline NDIS_STATUS
MapCtCounterToNl(PNL_BUFFER nlBuf,
                 UINT16 counterType,
                 OVS_CT_KEY *key)
{
    NDIS_STATUS status = NDIS_STATUS_SUCCESS;
    UINT32 offset = 0;

    offset = NlMsgStartNested(nlBuf, counterType);
    if (!offset) {
        return NDIS_STATUS_FAILURE;
    }

    if (!NlMsgPutTailU64(nlBuf, CTA_COUNTERS_PACKETS,
                         htonll(key->packetCount))) {
        status = NDIS_STATUS_FAILURE;
        goto done;
    }

    if (!NlMsgPutTailU64(nlBuf, CTA_COUNTERS_BYTES,
                         htonll(key->byteCount))) {
        status = NDIS_STATUS_FAILURE;
        goto done;
    }

done:
    NlMsgEndNested(nlBuf, offset);
    return status;
}

/* Userspace expects system time to be Unix timestamp in Nano Seconds */
static __inline unsigned
WindowsTickToUnixSeconds(long long windowsTicks)
{
    /*
     *  Windows epoch starts 1601-01-01T00:00:00Z. It's 11644473600 seconds
     *  before the UNIX/Linux epoch (1970-01-01T00:00:00Z). Windows ticks are
     *  in 100 nanoseconds
     */
    return (unsigned)((windowsTicks / WINDOWS_TICK
                        - SEC_TO_UNIX_EPOCH));
}

NTSTATUS
OvsCreateNlMsgFromCtEntry(POVS_CT_ENTRY entry,
                          PVOID outBuffer,
                          UINT32 outBufLen,
                          UINT8 eventType,
                          UINT32 nlmsgSeq,
                          UINT32 nlmsgPid,
                          UINT8 nfGenVersion,
                          UINT32 dpIfIndex)
{
    NL_BUFFER nlBuf;
    BOOLEAN ok;
    PNL_MSG_HDR nlMsg;
    UINT32 timeout;
    NDIS_STATUS status;
    UINT64 currentTime, expiration;
    UINT16 nlmsgType;
    UINT16 nlmsgFlags = NLM_F_CREATE;
    NdisGetCurrentSystemTime((LARGE_INTEGER *)&currentTime);
    UINT8 nfgenFamily = 0;
    if (entry->key.dl_type == htons(ETH_TYPE_IPV4)) {
        nfgenFamily = AF_INET;
    } else if (entry->key.dl_type == htons(ETH_TYPE_IPV6)) {
        nfgenFamily = AF_INET6;
    }

    NlBufInit(&nlBuf, outBuffer, outBufLen);
    /* Mimic netfilter */
    if (eventType == OVS_EVENT_CT_NEW || eventType == OVS_EVENT_CT_UPDATE) {
        nlmsgType = (UINT16) (NFNL_SUBSYS_CTNETLINK << 8 | IPCTNL_MSG_CT_NEW);
    } else if (eventType == OVS_EVENT_CT_DELETE) {
        nlmsgType = (UINT16) (NFNL_SUBSYS_CTNETLINK << 8 | IPCTNL_MSG_CT_DELETE);
    } else {
        return STATUS_INVALID_PARAMETER;
    }

    if (eventType == OVS_EVENT_CT_UPDATE) {
        /* In netlink-conntrack.c IPCTNL_MSG_CT_NEW msg type is used to
         * differentiate between OVS_EVENT_CT_NEW and OVS_EVENT_CT_UPDATE
         * events based on nlmsgFlags, unset it to notify an update event.
         */
        nlmsgFlags = 0;
    }
    ok = NlFillOvsMsgForNfGenMsg(&nlBuf, nlmsgType, nlmsgFlags,
                                 nlmsgSeq, nlmsgPid, nfgenFamily,
                                 nfGenVersion, dpIfIndex);
    if (!ok) {
        return STATUS_INVALID_BUFFER_SIZE;
    }

    status = MapCtKeyTupleToNl(&nlBuf, CTA_TUPLE_ORIG, &entry->key);
    if (status != NDIS_STATUS_SUCCESS) {
        return STATUS_UNSUCCESSFUL;
    }

    status = MapCtKeyTupleToNl(&nlBuf, CTA_TUPLE_REPLY, &entry->rev_key);
    if (status != NDIS_STATUS_SUCCESS) {
        return STATUS_UNSUCCESSFUL;
    }

    status = MapCtCounterToNl(&nlBuf, CTA_COUNTERS_ORIG, &entry->key);
    if (status != NDIS_STATUS_SUCCESS) {
        return STATUS_UNSUCCESSFUL;
    }

    status = MapCtCounterToNl(&nlBuf, CTA_COUNTERS_REPLY, &entry->rev_key);
    if (status != NDIS_STATUS_SUCCESS) {
        return STATUS_UNSUCCESSFUL;
    }

    if (entry->key.zone) {
        if (!NlMsgPutTailU16(&nlBuf, CTA_ZONE, htons(entry->key.zone))) {
            return STATUS_INVALID_BUFFER_SIZE;
        }
    }

    if (entry->mark) {
        if (!NlMsgPutTailU32(&nlBuf, CTA_MARK, htonl(entry->mark))) {
            return STATUS_INVALID_BUFFER_SIZE;
        }
    }

    if (entry->labels.ct_labels) {
        ok = NlMsgPutTailUnspec(&nlBuf, CTA_LABELS,
                                (PCHAR)(&entry->labels),
                                sizeof(entry->labels));
        if (!ok) {
            return STATUS_INVALID_BUFFER_SIZE;
        }
    }

    if (entry->expiration > currentTime) {
        expiration = entry->expiration - currentTime;
        timeout = (UINT32) (expiration / CT_INTERVAL_SEC);
        if (!NlMsgPutTailU32(&nlBuf, CTA_TIMEOUT, htonl(timeout))) {
            return STATUS_INVALID_BUFFER_SIZE;
        }
    }

    if (entry->key.nw_proto == IPPROTO_TCP) {
        /* Add ProtoInfo for TCP */
        UINT32 offset;
        offset = NlMsgStartNested(&nlBuf, CTA_PROTOINFO);
        if (!offset) {
            return NDIS_STATUS_FAILURE;
        }

        status = OvsCtMapTcpProtoInfoToNl(&nlBuf, entry);
        NlMsgEndNested(&nlBuf, offset);
        if (status != NDIS_STATUS_SUCCESS) {
            return STATUS_UNSUCCESSFUL;
        }
    }

    /* CTA_STATUS is required but not implemented. Default to 0 */
    if (!NlMsgPutTailU32(&nlBuf, CTA_STATUS, 0)) {
        return STATUS_INVALID_BUFFER_SIZE;
    }

    /* Mimic netfilter - nf_conntrack_netlink.c:
     *
     * int ctnetlink_dump_id(struct sk_buff *skb, const struct nf_conn *ct) {
     *     NLA_PUT_BE32(skb, CTA_ID, htonl((unsigned long)ct));
     *     return 0;
     * }
     *
     */
    if(!NlMsgPutTailU32(&nlBuf, CTA_ID, htonl((UINT32) entry))) {
        return STATUS_INVALID_BUFFER_SIZE;
    }

    if (entry->timestampStart) {
        UINT32 offset;
        offset = NlMsgStartNested(&nlBuf, CTA_TIMESTAMP);
        if (!offset) {
            return NDIS_STATUS_FAILURE;
        }
        UINT64 start;
        start = WindowsTickToUnixSeconds(entry->timestampStart);
        start = start * SEC_TO_NANOSEC;
        if (!NlMsgPutTailU64(&nlBuf, CTA_TIMESTAMP_START, htonll(start))) {
            NlMsgEndNested(&nlBuf, offset);
            return STATUS_INVALID_BUFFER_SIZE;
        }

        NlMsgEndNested(&nlBuf, offset);
    }

    nlMsg = (PNL_MSG_HDR)NlBufAt(&nlBuf, 0, 0);
    nlMsg->nlmsgLen = NlBufSize(&nlBuf);

    return STATUS_SUCCESS;
}

/*
 *----------------------------------------------------------------------------
 *  OvsCtDumpCmdHandler --
 *    Handler for IPCTNL_MSG_CT_GET command.
 *
 *  XXX - Try to consolidate dump handler patterns around dumpState usage
 *        The following dumpHandler is similar to one vport.c uses
 *----------------------------------------------------------------------------
*/
NTSTATUS
OvsCtDumpCmdHandler(POVS_USER_PARAMS_CONTEXT usrParamsCtx,
                    UINT32 *replyLen)
{
    NTSTATUS rc;
    /* Setup Dump Start if it's OVS_WRITE_DEV_OP and return */
    if (usrParamsCtx->devOp == OVS_WRITE_DEV_OP) {
        *replyLen = 0;
        OvsSetupDumpStart(usrParamsCtx);
        return STATUS_SUCCESS;
    }

    POVS_OPEN_INSTANCE instance =
        (POVS_OPEN_INSTANCE)usrParamsCtx->ovsInstance;
    POVS_MESSAGE msgIn;

    ASSERT(usrParamsCtx->devOp == OVS_READ_DEV_OP);
    if (instance->dumpState.ovsMsg == NULL) {
        ASSERT(FALSE);
        return STATUS_INVALID_DEVICE_STATE;
    }

    /* Output buffer has been validated while validating read dev op. */
    ASSERT(usrParamsCtx->outputBuffer != NULL);
    msgIn = instance->dumpState.ovsMsg;
    UINT32 inBucket = instance->dumpState.index[0];
    UINT32 inIndex = instance->dumpState.index[1];
    UINT32 i = CT_HASH_TABLE_SIZE;
    UINT32 outIndex = 0;

    LOCK_STATE_EX lockState;
    NdisAcquireRWLockRead(ovsConntrackLockObj, &lockState, 0);

    if (ctTotalEntries) {
        for (i = inBucket; i < CT_HASH_TABLE_SIZE; i++) {
            PLIST_ENTRY head, link;
            head = &ovsConntrackTable[i];
            POVS_CT_ENTRY entry = NULL;

            outIndex = 0;
            LIST_FORALL(head, link) {
                /*
                 * if one or more dumps were previously done on this same
                 * bucket, inIndex will be > 0, so we'll need to reply with
                 * the inIndex + 1 ct-entry from the bucket.
                 */
                if (outIndex >= inIndex) {
                    entry = CONTAINING_RECORD(link, OVS_CT_ENTRY, link);

                    rc = OvsCreateNlMsgFromCtEntry(entry,
                                                   usrParamsCtx->outputBuffer,
                                                   usrParamsCtx->outputLength,
                                                   OVS_EVENT_CT_NEW,
                                                   msgIn->nlMsg.nlmsgSeq,
                                                   msgIn->nlMsg.nlmsgPid,
                                                   msgIn->nfGenMsg.version,
                                                   0);

                    if (rc != NDIS_STATUS_SUCCESS) {
                        NdisReleaseRWLock(ovsConntrackLockObj, &lockState);
                        return STATUS_UNSUCCESSFUL;
                    }

                    ++outIndex;
                    break;
                }

                ++outIndex;
            }

            if (entry) {
                break;
            }

            /*
             * if no ct-entry was found above, check the next bucket, beginning
             * with the first (i.e. index 0) elem from within that bucket
             */
            inIndex = 0;
        }
    }
    instance->dumpState.index[0] = i;
    instance->dumpState.index[1] = outIndex;
    NdisReleaseRWLock(ovsConntrackLockObj, &lockState);

    /* if i < CT_HASH_TABLE_SIZE => entry was found */
    if (i < CT_HASH_TABLE_SIZE) {
        POVS_MESSAGE msgOut = (POVS_MESSAGE)usrParamsCtx->outputBuffer;
        *replyLen = msgOut->nlMsg.nlmsgLen;
    } else {
        /* if i >= CT_HASH_TABLE_SIZE => entry was not found => dump done */
        *replyLen = 0;
        FreeUserDumpState(instance);
    }

    return STATUS_SUCCESS;
}

#pragma warning(pop)
