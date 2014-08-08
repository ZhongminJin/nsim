"""Example of using a model defined with a single complex variable.

dz = (-z + j (delta + g cos(omega t)) z + j epsilon) dt + sigma exp(4jt) dW

With parameters below the system has noise driven oscillations around a stable
fixed point.

Using complex vector variables is ok, too. (numpy arrays of complex128)
nsim will look at y0 to determine what type of variable is being used.
"""

import nsim
import numpy as np


class Osc(nsim.SDEModel):
    delta = 2.0
    epsilon = 100.0
    sigma = 10.0
    g = 1.0
    omega = 2.0
    y0 = 0.0 + 0.0j

    def f(self, y, t):
        return (-y + 1j*(self.delta + self.g*np.cos(self.omega*t))*y +
                1j*self.epsilon)

    def G(self, y, t):
        return self.sigma * np.exp(4j*t)
    

sims = nsim.RepeatedSim(Osc, T=1440.0, repeat=10)

ts = sims.timeseries

means = np.array([ts.mean(axis=0) for s in sims]).mean()
phases = (ts - means).angle()
phases.plot(title='phase at each node')
phases[:,:,1].t[300:360].plot(title='phase') # show 60 seconds of node 1

print('mean period is %g seconds' % phases[:,:,1].periods().mean())
