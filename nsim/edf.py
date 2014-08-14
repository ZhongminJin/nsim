# Copyright 2014 Matthew J. Aburn
# 
# This program is free software: you can redistribute it and/or modify 
# it under the terms of the GNU General Public License as published by 
# the Free Software Foundation, either version 3 of the License, or 
# (at your option) any later version. See <http://www.gnu.org/licenses/>.

"""
functions:
  timeseries_from_edf()   load a multi-channel Timeseries from an EDF file
"""

from __future__ import absolute_import
import edflib
import nsim
import numpy as np
from os import path

def timeseries_from_edf(filename):
    """load a multi-channel Timeseries from an EDF (European Data Format) file

    Args: 
      filename: EDF file

    Returns: 
      Timeseries
    """
    if not path.isfile(filename):
        raise nsim.Error("file not found: '%s'" % filename)
    e = edflib.EDF(filename)
    if np.ptp(e.signal_nsamples) != 0:
        raise nsim.Error('channels have differing numbers of samples')
    if np.ptp(e.samplefreqs) != 0:
        raise nsim.Error('channels have differing sample rates')
    n = max(e.signal_nsamples)
    m = e.signals_in_file
    channelnames = e.signal_labels
    dt = 1.0/e.samplefreqs[0]
    # edflib requires input buffer of float64s
    ar = np.zeros((n, m), dtype=np.float64, order='F')
    for i in range(m):
        e.edf.readsignal(i, 0, n, ar[:, i])
    # EDF files hold <=16 bits of information for each sample. Representing as
    # double precision (64bit) is unnecessary use of memory. use 32 bit float:
    ar = ar.astype(np.float32)
    tspan = np.arange(0, (n - 1 + 0.5) * dt, dt, dtype=np.float32)
    return nsim.Timeseries(ar, tspan, labels=[None, channelnames])
