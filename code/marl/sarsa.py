import numpy as np
import random
import tilecoding.representation as r
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
				extended_mins=[], extended_maxes=[]):
		state_range = [
			[0 for i in xrange(vec_size)] + extended_mins,
			[max_bw for i in xrange(vec_size)]+ extended_maxes,
		]
		self.tc = r.TileCoding(
			input_indices = [np.arange(vec_size)],
			ntiles = [tile_c],
			ntilings = [tilings_c],
			hashing = None,
			state_range = state_range,
			rnd_stream = np.random.RandomState(),
		)

		self.epsilon = epsilon
		self._curr_epsilon = epsilon
		self.epsilon_falloff = epsilon_falloff

		self.learn_rate = learn_rate
		self.discount = discount

		self.actions = actions
		self.break_equal = break_equal
		self.values = {}
		self.default_q = float(default_q)

		self._step_count = 0

	def _ensure_state_vals_exist(self, state):
		for tile in state:
			if tile not in self.values:
				self.values[tile] = np.full(len(self.actions), float(self.default_q))

	def _get_state_values(self, state):
		self._ensure_state_vals_exist(state)
		return [self.values[tile] for tile in state]

	def _update_state_values(self, state, action, values):
		self._ensure_state_vals_exist(state)
		for tile, value in zip(state, values):
			self.values[tile][action] = value

	def select_action(self, state):
		all_tile_action_vals = self._get_state_values(state)

		# The value of each action iondividually
		action_vals = np.zeros(len(self.actions))
		for tile_av in all_tile_action_vals:
			action_vals += tile_av

		a_index = self.select_action_from_vals(action_vals)
		
		action = self.actions[a_index]

		# action, indiv. values for the action that was chosen, summed values for each action
		return (action, np.array([av[a_index] for av in all_tile_action_vals]))

	def select_action_from_vals(self, vals):
		# Epsilon-greedy action selection (linear-decreasing).
		if np.random.uniform() < self._curr_epsilon:
			a_index = np.random.randint(len(self.actions))
		elif self.break_equal:
			a_index = np.random.choice(np.flatnonzero(vals == vals.max()))
		else:
			a_index = np.argmax(vals)
		
		return a_index

	# Need to convert state with self.tc(...) first
	def bootstrap(self, state):
		# Select an action:
		(action, values) = self._select_action(state)

		self.last_act = (state, action, values)
		
		return action

	# Ditto. run self.tc(...) on state observation
	def update(self, state, reward, subs_last_act=None):
		(last_state, last_action) = (self.last_act if subs_last_act is None else subs_last_act)

		# because of updates in parallel, we need to grab the current values.
		# The update depends not on the value they once had, but only on the *current value* and the target (R).
		# Otherwise, we're moving from an old start to the new target...
		all_tile_action_vals = self._get_state_values(last_state)
		last_values = np.array([av[last_action] for av in all_tile_action_vals])

		# First, what is the value of the action would we choose in the new state w/ old model
		(new_action, new_values, ac_values) = self.select_action(state)

		updated_vals = last_values + (self.discount*new_values - last_values + reward) * self.learn_rate

		# Update value accordingly
		self._update_state_values(last_state, self.actions.index(last_action), updated_vals)

		# Reduce epsilon somehow
		self._curr_epsilon = max(0, (1 - self._step_count/float(self.epsilon_falloff)) * self.epsilon)
		self._step_count += 1

		self.last_act = (state, new_action)

		# Return the "chosen" action, and the values it was computed from.
		return (new_action, ac_values)

	def to_state(self, *args):
		out = self.tc(*args)
		return tuple(out)
