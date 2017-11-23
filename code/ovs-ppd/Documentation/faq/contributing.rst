..
      Licensed under the Apache License, Version 2.0 (the "License"); you may
      not use this file except in compliance with the License. You may obtain
      a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

      Unless required by applicable law or agreed to in writing, software
      distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
      WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
      License for the specific language governing permissions and limitations
      under the License.

      Convention for heading levels in Open vSwitch documentation:

      =======  Heading 0 (reserved for the title in a document)
      -------  Heading 1
      ~~~~~~~  Heading 2
      +++++++  Heading 3
      '''''''  Heading 4

      Avoid deeper levels because they do not render well.

===========
Development
===========

Q: How do I implement a new OpenFlow message?

    A: Add your new message to ``enum ofpraw`` and ``enum ofptype`` in
    ``include/openvswitch/ofp-msgs.h``, following the existing pattern.
    Then recompile and fix all of the new warnings, implementing new functionality
    for the new message as needed.  (If you configure with ``--enable-Werror``, as
    described in :doc:`/intro/install/general`, then it is impossible to miss any
    warnings.)

    To add an OpenFlow vendor extension message (aka experimenter message) for
    a vendor that doesn't yet have any extension messages, you will also need
    to edit ``build-aux/extract-ofp-msgs`` and at least ``ofphdrs_decode()``
    and ``ofpraw_put__()`` in ``lib/ofp-msgs.c``.  OpenFlow doesn't standardize
    vendor extensions very well, so it's hard to make the process simpler than
    that.  (If you have a choice of how to design your vendor extension
    messages, it will be easier if you make them resemble the ONF and OVS
    extension messages.)

Q: How do I add support for a new field or header?

    A: Add new members for your field to ``struct flow`` in ``lib/flow.h``, and
    add new enumerations for your new field to ``enum mf_field_id`` in
    ``include/openvswitch/meta-flow.h``, following the existing pattern.  If
    the field uses a new OXM class, add it to OXM_CLASSES in
    ``build-aux/extract-ofp-fields``.  Also, add support to
    ``miniflow_extract()`` in ``lib/flow.c`` for extracting your new field from
    a packet into struct miniflow, and to ``nx_put_raw()`` in
    ``lib/nx-match.c`` to output your new field in OXM matches.  Then recompile
    and fix all of the new warnings, implementing new functionality for the new
    field or header as needed.  (If you configure with ``--enable-Werror``, as
    described in :doc:`/intro/install/general`, then it is impossible to miss
    any warnings.)

    If you want kernel datapath support for your new field, you also need to
    modify the kernel module for the operating systems you are interested in.
    This isn't mandatory, since fields understood only by userspace work too
    (with a performance penalty), so it's reasonable to start development
    without it.  If you implement kernel module support for Linux, then the
    Linux kernel "netdev" mailing list is the place to submit that support
    first; please read up on the Linux kernel development process separately.
    The Windows datapath kernel module support, on the other hand, is
    maintained within the OVS tree, so patches for that can go directly to
    ovs-dev.

Q: How do I add support for a new OpenFlow action?

    A: Add your new action to ``enum ofp_raw_action_type`` in
    ``lib/ofp-actions.c``, following the existing pattern.  Then recompile and
    fix all of the new warnings, implementing new functionality for the new
    action as needed.  (If you configure with ``--enable-Werror``, as described
    in the :doc:`/intro/install/general`, then it is impossible to miss any
    warnings.)

    If you need to add an OpenFlow vendor extension action for a vendor that
    doesn't yet have any extension actions, then you will also need to add the
    vendor to ``vendor_map`` in ``build-aux/extract-ofp-actions``.  Also, you
    will need to add support for the vendor to ``ofpact_decode_raw()`` and
    ``ofpact_put_raw()`` in ``lib/ofp-actions.c``.  (If you have a choice of
    how to design your vendor extension actions, it will be easier if you make
    them resemble the ONF and OVS extension actions.)

Q: How do I add support for a new OpenFlow error message?

    A: Add your new error to ``enum ofperr`` in
    ``include/openvswitch/ofp-errors.h``.  Read the large comment at the top of
    the file for details.  If you need to add an OpenFlow vendor extension
    error for a vendor that doesn't yet have any, first add the vendor ID to
    the ``<name>_VENDOR_ID`` list in ``include/openflow/openflow-common.h``.
