# Copyright 2014 Matthew J. Aburn
# 
# This program is free software: you can redistribute it and/or modify 
# it under the terms of the GNU General Public License as published by 
# the Free Software Foundation, either version 3 of the License, or 
# (at your option) any later version. See <http://www.gnu.org/licenses/>.

"""
classes:

  Timeseries   numpy array with extra methods for time series analyses
"""

from __future__ import absolute_import
import numpy as np
import types
import numbers


class Timeseries(np.ndarray):
    """A numpy array with extra methods for applying time series analyses.
    It is an array of up to 3 dimensions.

    axis 0 ranges across values of the system at different points in time.
           For a single variable time series this is the only axis needed.

    axis 1, if present, ranges across the different variables/channels of a 
            multivariate time series, at a single node.

    axis 2, if present, ranges across different nodes of a network simulation 
            or repeated simulation.                  

    Thus the shape of a Timeseries array is (N, n, m) where N is the 
    total number of time steps, n is the number of variables of a single node 
    and m is the number of nodes.

    Slice by sample index:    timeseries[103280:104800]
    Slice by time in seconds: timeseries.t[10.0:20.0]

    Methods:
      All functions defined in the package nsim.analyses1 are available as 
      methods of the Timeseries  (as well as the usual methods of numpy arrays)

      Your own analysis functions can also be included by calling
      Timeseries.add_analyses('file.py')
    
    Attributes:
      tspan: An array of shape (N,) defining the time in seconds that is 
             meant by each time point. This should always remain sorted.
      channelnames (array of str, optional): Name of each channel/variable
    """
    def __new__(cls, input_array, tspan=None, fs=None, channelnames=None):
        #print('In __new__')
        obj = np.asarray(input_array).view(cls)
        if tspan is not None:
            obj.tspan = tspan
        elif isinstance(input_array, Timeseries):
            obj.tspan = input_array.tspan
        else:
            if fs is None:
                fs = 1.0
            n = len(input_array)
            obj.tspan = np.linspace(0.0, 1.0*(n-1)/fs, n, endpoint=True)
        if isinstance(input_array, Timeseries) and channelnames is None:
            obj.channelnames = input_array.channelnames
        else:
            obj.channelnames = channelnames
        if isinstance(channelnames, list): # TODO: clean this up
            obj.channelnames = np.array(channelnames)
        if obj.channelnames is None:
            if input_array.ndim is 1:
                obj.channelnames = np.array([''])
            else:
                obj.channelnames = np.array([''] * input_array.shape[1])
        obj.t = _Timeslice(obj)
        return obj

    def __init__(self, input_array, tspan=None, channelnames=None):
        #print('In __init__')
        pass

    @classmethod
    def add_analyses(cls, source):
        """Dynamically add new analysis methods to the Timeseries class.
        Args:
          source: Can be a function, module or the filename of a python file.
            If a filename or a module is given, then all functions defined 
            inside not starting with _ will be added as methods.

        The only restriction on the functions is that they can accept a 
        Timeseries as their first argument. So existing functions that 
        take a ndarray or array or even a list will usually also work.
        """
        if isinstance(source, types.FunctionType):
            _add_single_method(source.__name__, source)
        else:
            if isinstance(source, types.ModuleType):
                mod = source
            elif isinstance(source, types.StringTypes):
                import os
                import imp
                path = os.path.abspath(source)
                if os.path.isfile(path) and path[-3:] == '.py':
                    dir, file = os.path.split(path)
                    name = file[:-3]
                    module_info = imp.find_module(name, [dir])
                    mod = imp.load_module('nsim.' + name, *module_info)
                elif (os.path.isdir(path) and 
                        '__init__.py' in os.listdir(path)):
                    module_info = imp.find_module('__init__', [path])
                    name = os.path.basename(path)
                    mod = imp.load_module('nsim.' + name, *module_info)
                else:
                    raise Error('"%s" is not a file or directory' % source)
            else:
                raise ValueError('`source` argument not a function or module')
            for name, obj in mod.__dict__.items():
                if name[0] != '_' and isinstance(obj, types.FunctionType):
                    cls._add_single_method(name, obj)

    @classmethod
    def _add_single_method(cls, name, f):
        import sys
        setattr(cls, name, f)
        #If using RemoteTimeseries, add method to that class too:
        if 'distob' in sys.modules:
            import distob
            if distob.engine is not None and cls in distob.engine.proxy_types:
                RemoteClass = distob.engine.proxy_types[cls]
                def mk_proxy_method(method_name, doc):
                    def method(self, *args, **kwargs):
                        if self._obcache_current:
                            return getattr(self._obcache, method_name)(
                                    *args, **kwargs)
                        else:
                            return self._try_cached_apply(
                                    method_name, *args, **kwargs)
                    method.__doc__ = doc
                    method.__name__ = method_name
                    return method
                remotemethod = mk_proxy_method(name, f.__doc__)
                setattr(RemoteClass, name, remotemethod)
                # also update class definitions on remote engines
                if isinstance(distob.engine, distob.ObjectHub):
                    dv = distob.engine._dv
                    def remote_update(name, Class, f, remotemethod):
                        setattr(Class, name, f)
                        RemoteClass = distob.engine.proxy_types[Class]
                        setattr(RemoteClass, name, remotemethod)
                    ars = self._dv.apply(remote_uptdae, real_type, proxy_type)
                    self._dv.wait(ars)
                    for ar in ars:
                        if not ar.successful():
                            raise ar.r

    def __array_finalize__(self, obj):
        #print('In __array_finalize__, obj is type ' + str(type(obj)))
        if obj is None:
            return
        if isinstance(obj, self.__class__):
            if obj.shape is () or obj.shape is not () and len(self) ==len(obj):
                self.tspan = obj.tspan
                self.channelnames = obj.channelnames

    def __array_prepare__(self, in_arr, context=None):
        #print('In __array_prepare__')
        return super(Timeseries, self).__array_prepare__(in_arr, context)

    def __array_wrap__(self, out_arr, context=None):
        #print('In __array_wrap__')
        return super(Timeseries, self).__array_wrap__(out_arr, context)

    def __getitem__(self, index):
        """When a Timeseries is sliced, tspan will also be sliced in the 
        same way as axis 0 of the Timeseries.
        channelnames will be sliced in the same way as axis 1.
        If the resulting array is not a Timeseries then return an ndarray.
        """
        #TODO add support for multidimensional array indexing
        #print('In __getitem__, index is ' + str(index))
        new_array = np.asarray(self).__getitem__(index)
        is_ts = True
        if (isinstance(index, numbers.Integral) or 
                isinstance(index, types.SliceType) or
                isinstance(index, types.EllipsisType) or 
                isinstance(index, np.ndarray) and index.ndim is 1):
            new_tspan = self.tspan[index]
            new_channelnames = self.channelnames
        elif isinstance(index, types.TupleType):
            if Ellipsis in index:
                pos = index.index(Ellipsis)
                while len(index) < self.ndim:
                    index = index[:pos] + (slice(None),)*2 + index[(pos+1):]
            if self.tspan.shape is ():
                new_tspan = None
                new_channelnames = None
                is_ts = False
            else:
                new_tspan = self.tspan[index[0]]
            if len(index) > 1:
                new_channelnames = self.channelnames[index[1]]
                if not isinstance(new_channelnames, np.ndarray):
                    if new_array.ndim is 1:
                        new_channelnames = np.array([''])
                    else:
                        new_channelnames = np.array([''] * new_array.shape[1])
            else:
                new_channelnames = self.channelnames
        elif index is None:
            is_ts = False
        if not isinstance(new_tspan, np.ndarray):
            is_ts = False
        if is_ts:
            return Timeseries(new_array, new_tspan, new_channelnames)
        else:
            return np.asarray(new_array)

    def __setitem__(self, index, value):
        #print('in __setitem__')
        return super(Timeseries, self).__setitem__(index, value)

    def __getslice__(self, i, j):
        #print('in __getslice__')
        return self.__getitem__(slice(i, j, None))

    def __setslice__(self, i, j, value):
        #print('in __setslice__')
        return self.__setitem__(slice(i, j, None), value)

    def __repr__(self):
        classname = self.__class__.__name__
        if self.tspan.shape is ():
            first = last = self.tspan
        else:
            first = self.tspan[0]
            last = self.tspan[-1]
        head = u'<%s of shape %s from time %f to %f>:\n' % (
            classname, self.shape, first, last)
        repr_tspan = repr(self.tspan)
        if len(repr_tspan) > 160:
            repr_tspan = 'array([ %f, ..., %f ])' % (first, last)
        content = repr(np.asarray(self)).replace('array', 
            classname, 1).rstrip(')') + ', \n        %s' % repr_tspan
        if np.alltrue(self.channelnames == ''):
            channames = ''
        else: 
            channames = ', \n        %s' % repr(self.channelnames)
        return head + content + channames + ')'

    def __reduce__(self):
        """Support pickling Timeseries instances by saving __dict__"""
        recon, initargs, state = super(Timeseries, self).__reduce__()
        tsstate = tuple((state, self.__dict__)) # nested, to avoid tuple copying
        return tuple((recon, initargs, tsstate))
        
    def __setstate__(self, tsstate):
        """Support unpickling Timeseries instances by loading __dict__"""
        super(Timeseries, self).__setstate__(tsstate[0])
        self.__dict__.update(tsstate[1])

    def angle(self, deg=0):
        return Timeseries(np.angle(self, deg=deg), self.tspan)

    # Some of the usual array operations on Timeseries return a plain ndarray. 
    # This depends on whether a time axis is present in the result:

    def flatten(self, order='C'):
        return np.asarray(self).flatten(order)

    def ravel(self, order='C'):
        return np.asarray(self).ravel(order)

    def swapaxes(self, axis1, axis2):
        return np.asarray(self).swapaxes(axis1, axis2)

    def transpose(self, *axes):
        return np.asarray(self).transpose(*axes)

    def argmin(self, axis=None, out=None):
        return np.asarray(self).argmin(axis, out)

    def argmax(self, axis=None, out=None):
        return np.asarray(self).argmax(axis, out)

    def reshape(self, newshape, order='C'):
        """If axis 0 is unaffected by the reshape, then returns a Timeseries,
        otherwise returns an ndarray. See numpy.ndarray.reshape() for details.
        """
        oldshape = self.shape
        if (newshape is -1 and len(oldshape) is 1 or
                (isinstance(newshape, numbers.Integral) and 
                    newshape == oldshape[0]) or 
                (isinstance(newshape, types.TupleType) and 
                    (newshape[0] == oldshape[0] or 
                     (newshape[0] is -1 and np.array(oldshape[1:]).prod() == 
                                            np.array(newshape[1:]).prod())))):
            # then axis 0 is unaffected by the reshape
            return super(Timeseries, self).reshape(newshape, order=order)
        else:
            return np.asarray(self).reshape(newshape, order=order)

    def min(self, axis=None, out=None):
        if (axis is 0 or 
                self.ndim is 1 or 
                isinstance(axis, types.TupleType) and 0 in axis):
            return np.asarray(self).min(axis, out)
        else:
            return super(Timeseries, self).min(axis, out)

    def max(self, axis=None, out=None):
        if (axis is 0 or 
                self.ndim is 1 or 
                isinstance(axis, types.TupleType) and 0 in axis):
            return np.asarray(self).max(axis, out)
        else:
            return super(Timeseries, self).max(axis, out)

    def ptp(self, axis=None, out=None):
        if (axis is 0 or 
                self.ndim is 1 or 
                isinstance(axis, types.TupleType) and 0 in axis):
            return np.asarray(self).ptp(axis, out)
        else:
            return super(Timeseries, self).ptp(axis, out)

    def mean(self, axis=None, dtype=None, out=None):
        if (axis is 0 or 
                self.ndim is 1 or 
                isinstance(axis, types.TupleType) and 0 in axis):
            return np.asarray(self).mean(axis, dtype, out)
        else:
            return super(Timeseries, self).mean(axis, dtype, out)

    def std(self, axis=None, dtype=None, out=None, ddof=0):
        if (axis is 0 or 
                self.ndim is 1 or 
                isinstance(axis, types.TupleType) and 0 in axis):
            return np.asarray(self).std(axis, dtype, out, ddof)
        else:
            return super(Timeseries, self).std(axis, dtype, out, ddof)

    def var(self, axis=None, dtype=None, out=None, ddof=0):
        if (axis is 0 or 
                self.ndim is 1 or 
                isinstance(axis, types.TupleType) and 0 in axis):
            return np.asarray(self).var(axis, dtype, out, ddof)
        else:
            return super(Timeseries, self).var(axis, dtype, out, ddof)

    def merge(self, ts):
        """Merge another timeseries with this one
        Arguments:
          ts (Timeseries): The two timeseries being merged must have the
            same shape except for axis 0.
        Returns: 
          Resulting merged timeseries which can have duplicate time points.
        """
        if ts.shape[1:] != self.shape[1:]:
            raise ValueError('Timeseries to merge must have compatible shapes')
        indices = np.vstack((self.tspan, ts.tspan)).argsort()
        return np.vstack((self, ts))[indices]


class _Timeslice(object):
    """Implements the `t` attribute of Timeseries that allows slicing by time
    instead of by array index. For example, timeseries.t[9.5:30:0.1] 
    resamples the time range from t=9.5 to t=30 in 0.1 second increments.
    """
    def __init__(self, ts):
        """Args: ts: Timeseries"""
        self.ts = ts

    def __getitem__(self, index):
        #print('in timeslice getitem, index type %s, index is %s' % (
        #    type(index), repr(index)))
        ts = self.ts
        dt = (ts.tspan[-1] - ts.tspan[0]) / (len(ts) - 1)
        if isinstance(index, numbers.Number):
            newix = ts.tspan.searchsorted(index)
            return ts[newix]
        elif isinstance(index, types.SliceType):
            if index.step is None:
                start, stop = ts.tspan.searchsorted([index.start, index.stop])
                return ts[slice(start, stop, None)]
            else:
                n = np.floor_divide(index.start - index.stop, index.step)
                times = np.linspace(index.start, index.stop, n, endpoint=False)
                indices = ts.tspan.searchsorted(times)
                if indices[-1] == len(ts.tspan):
                    indices = indices[:-1]
                return ts[indices]
        elif isinstance(index, types.EllipsisType) or index is None:
            return ts[index]
        elif isinstance(index, np.ndarray) and index.ndim is 1:
            indices = ts.tspan.searchsorted(index)
            if indices[-1] == len(ts.tspan):
                indices = indices[:-1]
            return ts[indices]
        elif isinstance(index, types.TupleType):
            timeix = index[0]
            otherix = index[1:]
            if len(otherix) is 1:
                otherix = otherix[0]
            ts1 = ts.t[timeix]
            if ts1.ndim < ts.ndim:
                return ts1[otherix]
            else:
                return ts1[:, otherix]
        else:
            raise TypeError("Time slicing can't handle that type of index yet")

    def __setitem__(self, index, value):
        ts = self.ts
        dt = (ts.tspan[-1] - ts.tspan[0]) / (len(ts) - 1)
        if isinstance(index, numbers.Number):
            newix = ts.tspan.searchsorted(index)
            return ts.__setitem__(newix, value)
        elif isinstance(index, types.SliceType):
            if index.step is None:
                start, stop = ts.tspan.searchsorted(index.start, index.stop)
                return ts.__setitem__(slice(start, stop, None), value)
            else:
                n = np.floor_divide(index.start - index.stop, index.step)
                times = np.linspace(index.start, index.stop, n, endpoint=False)
                indices = ts.tspan.searchsorted(times)
                if indices[-1] == len(ts.tspan):
                    indices = indices[:-1]
                return ts.__setitem__(indices, value)
        elif isinstance(index, types.EllipsisType) or index is None:
            return ts.__setitem__(index, value)
        elif isinstance(index, np.ndarray) and index.ndim is 1:
            indices = ts.tspan.searchsorted(index)
            if indices[-1] == len(ts.tspan):
                indices = indices[:-1]
            return ts.__setitem__(indices, value)
        elif isinstance(index, types.TupleType):
            timeix = index[0]
            ts = ts.t[timeix]
            otherix = index[1:]
            return ts.__setitem__(otherix, value)
        else:
            raise TypeError("Time slicing can't handle that type of index yet")

    def __getslice__(self, i, j):
        return self.__getitem__(slice(i, j, None))

    def __setslice__(self, i, j, value):
        return self.__setitem__(slice(i, j, None), value)

    def __repr__(self):
        fs = (1.0*len(self.ts) - 1) / (self.ts.tspan[-1] - self.ts.tspan[0])
        s = u'Time range %g to %g with average sample rate %g Hz\n' % (
                self.ts.tspan[0], self.ts.tspan[-1], fs)
        return s


def merge(tup):
    """Merge several timeseries
    Arguments:
      tup: sequence of Timeseries, with the same shape except for axis 0
    Returns: 
      Resulting merged timeseries which can have duplicate time points.
    """
    if not all(tuple(ts.shape[1:] == tup[0].shape[1:] for ts in tup[1:])):
        raise ValueError('Timeseries to merge must have compatible shapes')
    indices = np.vstack(tuple(ts.tspan for ts in tup)).argsort()
    return np.vstack((tup))[indices]


def timeseries_from_mat(filename, varname=None, fs=1.0):
    """load a multi-channel Timeseries from a MATLAB .mat file

    Args:
      filename (str): .mat file to load
      varname (str): variable name. only needed if there is more than one
        variable saved in the .mat file
      fs (scalar): sample rate of timeseries in Hz. (constant timestep assumed)

    Returns:
      Timeseries
    """
    import scipy.io as sio
    if varname is None:
        mat_dict = sio.loadmat(filename)
        if len(mat_dict) > 1:
            raise ValueError('Must specify varname: file contains '
                             'more than one variable. ')
    else:
        mat_dict = sio.loadmat(filename, variable_names=(varname,))
        array = mat_dict.popitem()[1]
    return Timeseries(array, fs=fs)
