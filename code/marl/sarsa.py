import numpy as np
import random
import tilecoding.representation as r
from spf import *
import sys

class SarsaLearner:
	"""Learning agent powered by Sarsa and Tile Coding, with e-greedy
			Assumes that actions are discretised, but states are continuous.
	"""
	# Tilings taken from
	# http://etheses.whiterose.ac.uk/8109/1/phd-thesis-malialis.pdf
	# Section 4.3
	def __init__(self, max_bw, vec_size, actions,
				epsilon=0.3, learn_rate=0.05, discount=0,
				tile_c=6, tilings_c=8, default_q=0.0,
				epsilon_falloff=1000,
				break_equal=False,
				extended_mins=[], extended_maxes=[],
				tc_indices=None,
				trace_decay=0.0, trace_threshold=0.0001,
				broken_math=False,
				rescale_alpha=1.0,
				increase_fixed_math_alpha_if_narrowed=True,
				always_include_bias=True,
				AcTrans=MarlMachine):
		state_range = [
			[0 for i in xrange(vec_size)] + extended_mins,
			[max_bw for i in xrange(vec_size)]+ extended_maxes,
		]

		tc_indices = tc_indices if tc_indices is not None else [np.arange(vec_size)]
		ntiles = [tile_c for _ in tc_indices]
		ntilings = [tilings_c for _ in tc_indices]
		self.ntilings = ntilings
		self.tiling_set_count = len(tc_indices)

		#print "tc has been configured with indices", tc_indices, "tiles", ntiles, "tilings", ntilings

		self.tc = r.TileCoding(
			input_indices = tc_indices, 
			# FIXME: allow arbitrary tile settings.
			ntiles = ntiles,
			ntilings = ntilings,
			hashing = None,
			state_range = state_range,
			rnd_stream = np.random.RandomState(),
		)
		# We need access to this again if we perform feature fixation.
		self.single_learn_rate = learn_rate

		if rescale_alpha is not None and not broken_math:
			# bias tile always exists.
			learn_rate = (learn_rate * rescale_alpha) / float(sum(ntilings) + 1)

		self.epsilon = epsilon
		self._curr_epsilon = epsilon
		self.epsilon_falloff = epsilon_falloff

		self.learn_rate = learn_rate
		self.discount = discount

		self.actions = actions
		self.break_equal = break_equal
		self.values = {}
		self.default_q = float(default_q)

		self._argmax_in_dt = False
		self._wipe_trace_if_not_argmax = False
		self.alpha_mod_fixed_math = increase_fixed_math_alpha_if_narrowed
		self.always_include_bias = always_include_bias

		self.trace_decay = trace_decay
		self.trace_threshold = trace_threshold

		# in case I ever need to return to the bug in the update rule for verification...
		self.broken_math = broken_math

		self._step_count = 0

	def _ensure_state_vals_exist(self, state):
		for tile in state:
			if tile not in self.values:
				self.values[tile] = np.full(len(self.actions), float(self.default_q))

	def _get_state_values(self, state):
		self._ensure_state_vals_exist(state)
		return [self.values[tile] for tile in state]

	def _update_state_values(self, state, action, values, narrowing):
		self._ensure_state_vals_exist(state)

		if narrowing is None:
			narrowing = xrange(len(state))

		# Why does this work?
		# Action computed using only these values, we then compute the delta
		# (using ALL values) and only propagate forward changes on the relevant tiles.
		for i in narrowing:
			tile = state[i]
			value = values[i]
			self.values[tile][action] = value

	def _compute_relevant_narrowed_tilings(self, narrowing):
		# Go from list of feature indices to list of the tilings connected
		out = []
		total = 0

		# assume, for all our sakes, that the narrowing is sorted...
		n_i = 0
		for i, length in enumerate(self.ntilings):
			if n_i < len(narrowing) and i == narrowing[n_i]:
				# hit an included element
				out.append(np.arange(total, total+length))
				n_i += 1
			total += length

		if self.always_include_bias:
			out.append(np.array([total]))

		return np.hstack(out) 

	def select_action(self, state, narrowing=None):
		# returns the action value estimate *from each tiling* as a list.
		all_tile_action_vals = self._get_state_values(state)

		if narrowing is None:
			narrowing = xrange(len(all_tile_action_vals))

		# The value of each action individually -- sum of tilings' estimates.
		action_vals = np.zeros(len(self.actions))
		for tile_index in narrowing:
			action_vals += all_tile_action_vals[tile_index]
		
		a_index = self.select_action_from_vals(action_vals)
		
		action = self.actions[a_index]

		# action, indiv. values for the action that was chosen, indiv values for argmax, summed values for each action
		return (
			a_index,
			np.array([av[a_index] for av in all_tile_action_vals]),
			np.array([av[np.argmax(action_vals)] for av in all_tile_action_vals]),
			action_vals,
		)

	def select_action_from_vals(self, vals):
		# Epsilon-greedy action selection (linear-decreasing).
		if np.random.uniform() < self._curr_epsilon:
			a_index = np.random.randint(len(self.actions))
		elif self.break_equal:
			a_index = np.random.choice(np.flatnonzero(vals == vals.max()))
		else:
			a_index = np.argmax(vals)
		
		return a_index

	def get_epsilon(self):
		return self._curr_epsilon

	# Need to convert state with self.tc(...) first
	def bootstrap(self, state):
		# Select an action:
		(action, _, _, ac_values) = self.select_action(state)

		z = z_vec(state) if self.trace_decay > 0.0 else None
		self.last_act = (state, action, z)
		
		return (action, ac_values, z)

	# Ditto. run self.tc(...) on state observation
	def update(
		self,
		state,
		reward,
		subs_last_act=None,
		decay=True,
		delta_space=None,
		# Narrowings are arrays of indices...
		# Note: this will spill out as an effect upon the value of alpha
		# if using the traditional RL math. Ignore this for now.
		# FIXME: reconcile effect of narrowings upon learning rate when using 'intended' maths.
		action_narrowing=None,
		update_narrowing=None,
	):
		(last_state, last_action, last_z) = (self.last_act if subs_last_act is None else subs_last_act)

		# because of updates in parallel, we need to grab the current values.
		# The update depends not on the value they once had, but only on the *current value* and the target (R).
		# Otherwise, we're moving from an old start to the new target...
		all_tile_action_vals = self._get_state_values(last_state)
		last_values = np.array([av[last_action] for av in all_tile_action_vals])

		## slight complication -- interaction between last & next?
		# i.e. full -> reduced -> reduced -> full
		# Also, each part of the vector maps to several tiles
		if action_narrowing is not None:
			action_narrowing = self._compute_relevant_narrowed_tilings(action_narrowing)
		if update_narrowing is not None:
			update_narrowing = self._compute_relevant_narrowed_tilings(update_narrowing)

		# First, what is the value of the action would we choose in the new state w/ old model
		# NOTE: we need to compute action using the possibly narrowed set of values,
		# but we need ALL values to be made available when we are handling "transitions"
		# between narrowed/unnarrowed regions of the markov chain.
		(new_action, new_values, argmax_values, ac_values) = self.select_action(state, action_narrowing)

		next_vals = argmax_values if self._argmax_in_dt else new_values
		argmax_chosen = np.all(new_values == argmax_values)
		vec_d_t = self.discount * next_vals - last_values + reward
		scalar_d_t = self.discount * np.sum(next_vals) - np.sum(last_values) + reward

		if self.broken_math:
			d_t = vec_d_t
		else:
			d_t = scalar_d_t

		#print "state is:", len(state), "vals are:", len(new_values), "vd_t is:", vec_d_t.shape

		if delta_space is not None:
			delta_space.append(scalar_d_t)
			delta_space += list(vec_d_t)

		# In fixed math mode, we want to *concentrate* the learned update among the fewer
		# tiles who were responsible.
		alpha = self.learn_rate
		if not self.broken_math and self.alpha_mod_fixed_math and update_narrowing is not None:
			# May or may not be numerically stable, needs testing...
			alpha = self.single_learn_rate / float(len(update_narrowing))

		ad_t = alpha * d_t

		if last_z is None:
			updated_vals = last_values + ad_t
			self._update_state_values(last_state, last_action, updated_vals, update_narrowing)

			# Update value accordingly
			new_z = None
			#print "vals are:", updated_vals, "from:", last_values, "by:", d_t
		else:
			(old_indices, old_grads) = last_z
			if self._wipe_trace_if_not_argmax and not argmax_chosen:
				old_grads = np.array([]) 
				old_indices = tuple([])
			else:
				old_grads *= (self.trace_decay * self.discount)

			new_z = merge_z_vec(state, (old_indices, old_grads), self.trace_threshold)

			# use new_z[0] to get the action value vectors we need to mutate
			state_tiles_to_mutate = self._get_state_values(new_z[0])
			action_tile_vals = np.array([av[last_action] for av in state_tiles_to_mutate])
			updated_vals = action_tile_vals + ad_t * new_z[1]
			self._update_state_values(new_z[0], last_action, updated_vals, update_narrowing)
			print "vals are:", updated_values, "from:", action_tile_vals, "by:", d_t

		# Reduce epsilon somehow
		if decay:
			self.decay()

		self.last_act = (state, new_action, new_z)

		# Return the "chosen" action, and the values it was computed from.
		return (new_action, ac_values, new_z)

	def decay(self):
		self._curr_epsilon = max(0, (1 - self._step_count/float(self.epsilon_falloff)) * self.epsilon)
		self._step_count += 1

	def to_state(self, *args):
		out = self.tc(*args)
		return tuple(out)

class QLearner(SarsaLearner):
	def __init__(self, **args):
		SarsaLearner.__init__(self, **args)
		self._argmax_in_dt = True
		self._wipe_trace_if_not_argmax = True

def z_vec(index_list):
	return (index_list, np.ones(len(index_list)))

def merge_z_vec(s_new, l_old, thres):
	(s_old, z_old) = l_old
	i = 0
	j = 0
	out_s = []
	out_z = []
	s_last = -1 
	while i < len(s_new) or j < len(s_old):
		select_old = j < len(s_old) and (not i < len(s_new) or s_old[j] <= s_new[i])
		(s, val) = (s_old[j], z_old[j]) if select_old else (s_new[i], 1.0)

		if s == s_last:
			out_z[-1] += val
		else:
			out_s.append(s)
			out_z.append(val)

		s_last = s
		if select_old:
			j += 1
		else:
			i += 1

	i = len(out_s) - 1
	while i >= 0:
		if out_z[i] < thres:
			out_s.pop(i)
			out_z.pop(i)
		i -= 1

	return (tuple(out_s), np.array(out_z))
