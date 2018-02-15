import numpy as np
import random
import tilecoding.representation as r

class SarsaLearner:
	"""Learning agent powered by Sarsa and Tile Coding, with e-greedy
			Assumes that actions are discretised, but states are continuous.
	"""
	def __init__(self, max_bw, vec_size, actions,
				epsilon=0.3, learn_rate=0.05, discount=0,
				tile_c=16, tilings_c=3, default_q=0,
				epsilon_falloff=1000):
		state_range = [[0 for i in xrange(vec_size)], [max_bw for i in xrange(vec_size)]]
		self.tc = r.TileCoding(
			input_indices = [np.arange(vec_size)],
			ntiles = [tile_c],
			ntilings = [tilings_c],
			hashing = None,
			state_range = state_range,
			rnd_stream = np.random.RandomState()
		)

		self.epsilon = epsilon
		self._curr_epsilon = epsilon
		self.epsilon_falloff = epsilon_falloff

		self.learn_rate = learn_rate
		self.discount = discount

		self.actions = actions
		self.values = {}
		self.default_q = default_q

		self._step_count = 0

	def _ensure_state_vals_exist(self, state):
		if state not in self.values:
			self.values[state] = np.array([self.default_q for ac in self.actions])

	def _get_state_values(self, state):
		self._ensure_state_vals_exist(state)
		return self.values[state]

	def _update_state_value(self, state, action, value):
		self._ensure_state_vals_exist(state)
		self.values[state][action] = value

	def _select_action(self, state):
		action_vals = self._get_state_values(state)

		# Epsilon-greedy action selection (linear-decreasing).
		if random.random() < self._curr_epsilon:
			a_index = random.randint(0, len(self.actions)-1)
		else:
			a_index = np.argmax(action_vals)
		
		action = self.actions[a_index]

		return (action, action_vals[a_index])

	# Need to convert state with self.tc(...) first
	def bootstrap(self, state):
		# Select an action:
		(action, value) = self._select_action(state)

		self.last_act = (state, action, value)

		return action

	# Ditto. run self.tc(...) on state observation
	def update(self, state, reward):
		(last_state, last_action, last_value) = self.last_act

		# First, what is the value of the action would we choose in the new state w/ old model
		(new_action, new_value) = self._select_action(state)

		# Update value accordingly
		self._update_state_value(last_state, self.actions.index(last_action),
			last_value + self.learn_rate*(reward + self.discount*new_value - last_value)
		)

		# Reduce epsilon somehow
		self._curr_epsilon = (1 - self._step_count/float(self.epsilon_falloff)) * self.epsilon
		self._step_count += 1

		self.last_act = (state, new_action, new_value)

		return new_action

	def to_state(self, *args):
		return tuple(self.tc(*args))
