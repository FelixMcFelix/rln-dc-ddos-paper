class MarlMachine:
	"""
		not even a state machine, just an interface.
		action sets state, rather than more complex logic.
	"""
	def __init__(self,
			values=[float(i) / 10 for i in xrange(10)],
			init_state=0,
			ac_space_override=None
			):
		self._curr_state = init_state
		self._values = values
		self._max_state = len(values) - 1
		self.ac_space = range(len(values)) \
			if ac_space_override is not None \
			else ac_space_override

	def move(self, action):
		if action >= 0 and action <= self._max_state:
			self._curr_state = action

	def action(self):
		return self._values[self._curr_state]

class SpfMachine(MarlMachine):
	"""
		basically a state machine seeing whether
		encoding known info about how flows behave
		with an RL agent aids performance.
		Basically a defcon monitor - stay, up, down. [0, 1, 2]
	"""
	def __init__(self,
			values=[0.0, 0.05, 0.25, 0.50, 1.0],
			init_state=1,
			):
		MarlMachine.__init__(self, values, init_state, range(3))

	def move(self, action):
		#print "in:{} took:{}".format(self._curr_state, action)
		if action == 1 and self._curr_state > 0:
			self._curr_state -= 1
		elif action == 2 and self._curr_state < self._max_state:
			self._curr_state += 1
		#print "now:{}".format(self._curr_state)
