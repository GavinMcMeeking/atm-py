from copy import deepcopy as _deepcopy

import numpy as _np
import pandas as _pd
from scipy import integrate as _integrate

from atmPy.aerosols.size_distribution import moments as _sizedist_moment_conversion
from atmPy.general import timeseries as _timeseries
from atmPy.general import vertical_profile as _vertical_profile
from atmPy.radiation.mie_scattering import bhmie as _bhmie
# import atmPy.aerosols.size_distribution.sizedistribution as _sizedistribution
from  atmPy.aerosols.size_distribution import sizedistribution as _sizedistribution
import warnings as _warnings


# Todo: Docstring is wrong
# todo: This function can be sped up by breaking it apart. Then have OpticalProperties
#       have properties that call the subfunction on demand

def size_dist2optical_properties(op, sd, aod=False, noOfAngles=100):
    """
    !!!Tis Docstring need fixn
    Calculates the extinction crossection, AOD, phase function, and asymmetry Parameter for each layer.
    plotting the layer and diameter dependent extinction coefficient gives you an idea what dominates the overall AOD.

    Parameters
    ----------
    wavelength: float.
        wavelength of the scattered light, unit: nm
    n: float.
        Index of refraction of the scattering particles

    noOfAngles: int, optional.
        Number of scattering angles to be calculated. This mostly effects calculations which depend on the phase
        function.

    Returns
    -------
    OpticalProperty instance

    """

    # if not _np.any(sd.index_of_refraction):
    #     txt = 'Refractive index is not specified. Either set self.index_of_refraction or set optional parameter n.'
    #     raise ValueError(txt)
    # if not sd.sup_optical_properties_wavelength:
    #     txt = 'Please provied wavelength by setting the attribute sup_optical_properties_wavelength (in nm).'
    #     raise AttributeError(txt)

    sd.parameters4reductions._check_opt_prop_param_exist()
    wavelength = sd.parameters4reductions.wavelength.value
    n = sd.parameters4reductions.refractive_index.value
    out = {}
    sdls = sd.convert2numberconcentration()
    index = sdls.data.index
    dist_class = type(sdls).__name__

    if dist_class not in ['SizeDist','SizeDist_TS','SizeDist_LS']:
        raise TypeError('this distribution class (%s) can not be converted into optical property yet!'%dist_class)

    # determin if index of refraction changes or if it is constant
    if isinstance(n, _pd.DataFrame):
        n_multi = True
    else:
        n_multi = False
    if not n_multi:
        mie, angular_scatt_func = _perform_Miecalculations(_np.array(sdls.bincenters / 1000.), wavelength / 1000., n,
                                                           noOfAngles=noOfAngles)

    if aod:
        #todo: use function that does a the interpolation instead of the sum?!? I guess this can lead to errors when layers are very thick, since centers are used instea dof edges?
        AOD_layer = _np.zeros((len(sdls.layercenters)))

    extCoeffPerLayer = _np.zeros((len(sdls.data.index.values), len(sdls.bincenters)))
    scattCoeffPerLayer = _np.zeros((len(sdls.data.index.values), len(sdls.bincenters)))
    absCoeffPerLayer = _np.zeros((len(sdls.data.index.values), len(sdls.bincenters)))

    angular_scatt_func_effective = _pd.DataFrame()
    asymmetry_parameter_LS = _np.zeros((len(sdls.data.index.values)))

    #calculate optical properties for each line in the dataFrame
    for i, lc in enumerate(sdls.data.index.values):
        laydata = sdls.data.iloc[i].values # picking a size distribution (either a layer or a point in time)

        if n_multi:
            mie, angular_scatt_func = _perform_Miecalculations(_np.array(sdls.bincenters / 1000.), wavelength / 1000., n.iloc[i].values[0],
                                                               noOfAngles=noOfAngles)
        extinction_coefficient = _get_coefficients(mie.extinction_crossection, laydata)
        scattering_coefficient = _get_coefficients(mie.scattering_crossection, laydata)
        absorption_coefficient = _get_coefficients(mie.absorption_crossection, laydata)

        if aod:
            layerThickness = sdls.layerbounderies[i][1] - sdls.layerbounderies[i][0]
            AOD_perBin = extinction_coefficient * layerThickness
            AOD_layer[i] = AOD_perBin.values.sum()

        extCoeffPerLayer[i] = extinction_coefficient
        scattCoeffPerLayer[i] = scattering_coefficient
        absCoeffPerLayer[i] = absorption_coefficient

        scattering_cross_eff = laydata * mie.scattering_crossection

        pfe = (laydata * angular_scatt_func).sum(axis=1)  # sum of all angular_scattering_intensities

        x_2p = pfe.index.values
        y_2p = pfe.values

        # limit to [0,pi]
        y_1p = y_2p[x_2p < _np.pi]
        x_1p = x_2p[x_2p < _np.pi]

        y_phase_func = y_1p * 4 * _np.pi / scattering_cross_eff.sum()
        asymmetry_parameter_LS[i] = .5 * _integrate.simps(_np.cos(x_1p) * y_phase_func * _np.sin(x_1p), x_1p)
        angular_scatt_func_effective[
            lc] = pfe * 1e-12 * 1e6  # equivalent to extCoeffPerLayer # similar to  _get_coefficients (converts everthing to meter)

    if aod:
        out['AOD'] = AOD_layer[~ _np.isnan(AOD_layer)].sum()
        out['AOD_layer'] = _pd.DataFrame(AOD_layer, index=sdls.layercenters, columns=['AOD per Layer'])
        out['AOD_cum'] = out['AOD_layer'].iloc[::-1].cumsum().iloc[::-1]

    extCoeff_perrow_perbin = _pd.DataFrame(extCoeffPerLayer, index=index, columns=sdls.data.columns)
    scattCoeff_perrow_perbin = _pd.DataFrame(scattCoeffPerLayer, index=index, columns=sdls.data.columns)
    absCoeff_perrow_perbin = _pd.DataFrame(absCoeffPerLayer, index=index, columns=sdls.data.columns)

    # if dist_class == 'SizeDist_TS':
    #     out['extCoeff_perrow_perbin'] = timeseries.TimeSeries_2D(extCoeff_perrow_perbin)
    if dist_class == 'SizeDist':
        out['extCoeff_perrow_perbin'] = _timeseries.TimeSeries(extCoeff_perrow_perbin)
        out['scattCoeff_perrow_perbin'] = _timeseries.TimeSeries(scattCoeff_perrow_perbin)
        out['absCoeff_perrow_perbin'] = _timeseries.TimeSeries(absCoeff_perrow_perbin)
    else:
        out['extCoeff_perrow_perbin'] = extCoeff_perrow_perbin
        out['scattCoeff_perrow_perbin'] = scattCoeff_perrow_perbin
        out['absCoeff_perrow_perbin'] = absCoeff_perrow_perbin
    # extCoeff_perrow = pd.DataFrame(extCoeff_perrow_perbin.sum(axis=1), columns=['ext_coeff'])
    # if index.dtype == '<M8[ns]':
    #     out['extCoeff_perrow'] = timeseries.TimeSeries(extCoeff_perrow)
    # else:
    #     out['extCoeff_perrow'] = extCoeff_perrow

    out['parent_type'] = dist_class
    out['asymmetry_param'] = _pd.DataFrame(asymmetry_parameter_LS, index=index,
                                           columns=['asymmetry_param'])
    # out['asymmetry_param_alt'] = pd.DataFrame(asymmetry_parameter_LS_alt, index=sdls.layercenters, columns = ['asymmetry_param_alt'])
    # out['OptPropInstance']= OpticalProperties(out, self.bins)
    out['wavelength'] = wavelength
    out['index_of_refraction'] = n
    out['bin_centers'] = sdls.bincenters
    out['bins'] = sdls.bins
    out['binwidth'] = sdls.binwidth
    out['distType'] = sdls.distributionType
    out['angular_scatt_func'] = angular_scatt_func_effective.transpose()

    # if dist_class == 'SizeDist_TS':
    #     return OpticalProperties_TS(out, parent = sd)
    # elif dist_class == 'SizeDist_LS':
    #     return OpticalProperties_VP(out, parent= sd)
    return out

def DEPRECATED_size_dist2optical_properties(sd, aod=False, noOfAngles=100):
    """
    !!!Tis Docstring need fixn
    Calculates the extinction crossection, AOD, phase function, and asymmetry Parameter for each layer.
    plotting the layer and diameter dependent extinction coefficient gives you an idea what dominates the overall AOD.

    Parameters
    ----------
    wavelength: float.
        wavelength of the scattered light, unit: nm
    n: float.
        Index of refraction of the scattering particles

    noOfAngles: int, optional.
        Number of scattering angles to be calculated. This mostly effects calculations which depend on the phase
        function.

    Returns
    -------
    OpticalProperty instance

    """

    # if not _np.any(sd.index_of_refraction):
    #     txt = 'Refractive index is not specified. Either set self.index_of_refraction or set optional parameter n.'
    #     raise ValueError(txt)
    # if not sd.sup_optical_properties_wavelength:
    #     txt = 'Please provied wavelength by setting the attribute sup_optical_properties_wavelength (in nm).'
    #     raise AttributeError(txt)

    sd.optical_properties_settings._check()
    wavelength = sd.optical_properties_settings.wavelength.value
    n = sd.optical_properties_settings.refractive_index.value
    out = {}
    sdls = sd.convert2numberconcentration()
    index = sdls.data.index
    dist_class = type(sdls).__name__

    if dist_class not in ['SizeDist','SizeDist_TS','SizeDist_LS']:
        raise TypeError('this distribution class (%s) can not be converted into optical property yet!'%dist_class)

    # determin if index of refraction changes or if it is constant
    if isinstance(n, _pd.DataFrame):
        n_multi = True
    else:
        n_multi = False
    if not n_multi:
        mie, angular_scatt_func = _perform_Miecalculations(_np.array(sdls.bincenters / 1000.), wavelength / 1000., n,
                                                           noOfAngles=noOfAngles)

    if aod:
        #todo: use function that does a the interpolation instead of the sum?!? I guess this can lead to errors when layers are very thick, since centers are used instea dof edges?
        AOD_layer = _np.zeros((len(sdls.layercenters)))

    extCoeffPerLayer = _np.zeros((len(sdls.data.index.values), len(sdls.bincenters)))
    scattCoeffPerLayer = _np.zeros((len(sdls.data.index.values), len(sdls.bincenters)))
    absCoeffPerLayer = _np.zeros((len(sdls.data.index.values), len(sdls.bincenters)))

    angular_scatt_func_effective = _pd.DataFrame()
    asymmetry_parameter_LS = _np.zeros((len(sdls.data.index.values)))

    #calculate optical properties for each line in the dataFrame
    for i, lc in enumerate(sdls.data.index.values):
        laydata = sdls.data.iloc[i].values # picking a size distribution (either a layer or a point in time)

        if n_multi:
            mie, angular_scatt_func = _perform_Miecalculations(_np.array(sdls.bincenters / 1000.), wavelength / 1000., n.iloc[i].values[0],
                                                               noOfAngles=noOfAngles)
        extinction_coefficient = _get_coefficients(mie.extinction_crossection, laydata)
        scattering_coefficient = _get_coefficients(mie.scattering_crossection, laydata)
        absorption_coefficient = _get_coefficients(mie.absorption_crossection, laydata)

        if aod:
            layerThickness = sdls.layerbounderies[i][1] - sdls.layerbounderies[i][0]
            AOD_perBin = extinction_coefficient * layerThickness
            AOD_layer[i] = AOD_perBin.values.sum()

        extCoeffPerLayer[i] = extinction_coefficient
        scattCoeffPerLayer[i] = scattering_coefficient
        absCoeffPerLayer[i] = absorption_coefficient

        scattering_cross_eff = laydata * mie.scattering_crossection

        pfe = (laydata * angular_scatt_func).sum(axis=1)  # sum of all angular_scattering_intensities

        x_2p = pfe.index.values
        y_2p = pfe.values

        # limit to [0,pi]
        y_1p = y_2p[x_2p < _np.pi]
        x_1p = x_2p[x_2p < _np.pi]

        y_phase_func = y_1p * 4 * _np.pi / scattering_cross_eff.sum()
        asymmetry_parameter_LS[i] = .5 * _integrate.simps(_np.cos(x_1p) * y_phase_func * _np.sin(x_1p), x_1p)
        angular_scatt_func_effective[
            lc] = pfe * 1e-12 * 1e6  # equivalent to extCoeffPerLayer # similar to  _get_coefficients (converts everthing to meter)

    if aod:
        out['AOD'] = AOD_layer[~ _np.isnan(AOD_layer)].sum()
        out['AOD_layer'] = _pd.DataFrame(AOD_layer, index=sdls.layercenters, columns=['AOD per Layer'])
        out['AOD_cum'] = out['AOD_layer'].iloc[::-1].cumsum().iloc[::-1]

    extCoeff_perrow_perbin = _pd.DataFrame(extCoeffPerLayer, index=index, columns=sdls.data.columns)
    scattCoeff_perrow_perbin = _pd.DataFrame(scattCoeffPerLayer, index=index, columns=sdls.data.columns)
    absCoeff_perrow_perbin = _pd.DataFrame(absCoeffPerLayer, index=index, columns=sdls.data.columns)

    # if dist_class == 'SizeDist_TS':
    #     out['extCoeff_perrow_perbin'] = timeseries.TimeSeries_2D(extCoeff_perrow_perbin)
    if dist_class == 'SizeDist':
        out['extCoeff_perrow_perbin'] = _timeseries.TimeSeries(extCoeff_perrow_perbin)
        out['scattCoeff_perrow_perbin'] = _timeseries.TimeSeries(scattCoeff_perrow_perbin)
        out['absCoeff_perrow_perbin'] = _timeseries.TimeSeries(absCoeff_perrow_perbin)
    else:
        out['extCoeff_perrow_perbin'] = extCoeff_perrow_perbin
        out['scattCoeff_perrow_perbin'] = scattCoeff_perrow_perbin
        out['absCoeff_perrow_perbin'] = absCoeff_perrow_perbin
    # extCoeff_perrow = pd.DataFrame(extCoeff_perrow_perbin.sum(axis=1), columns=['ext_coeff'])
    # if index.dtype == '<M8[ns]':
    #     out['extCoeff_perrow'] = timeseries.TimeSeries(extCoeff_perrow)
    # else:
    #     out['extCoeff_perrow'] = extCoeff_perrow

    out['parent_type'] = dist_class
    out['asymmetry_param'] = _pd.DataFrame(asymmetry_parameter_LS, index=index,
                                           columns=['asymmetry_param'])
    # out['asymmetry_param_alt'] = pd.DataFrame(asymmetry_parameter_LS_alt, index=sdls.layercenters, columns = ['asymmetry_param_alt'])
    # out['OptPropInstance']= OpticalProperties(out, self.bins)
    out['wavelength'] = wavelength
    out['index_of_refraction'] = n
    out['bin_centers'] = sdls.bincenters
    out['bins'] = sdls.bins
    out['binwidth'] = sdls.binwidth
    out['distType'] = sdls.distributionType
    out['angular_scatt_func'] = angular_scatt_func_effective
    # opt_properties = OpticalProperties(out, self.bins)
    # opt_properties.wavelength = wavelength
    # opt_properties.index_of_refractio = n
    # opt_properties.angular_scatt_func = angular_scatt_func_effective  # This is the formaer phase_fct, but since it is the angular scattering intensity, i changed the name
    # opt_properties.parent_dist_LS = self
    if dist_class == 'SizeDist_TS':
        return OpticalProperties_TS(out, parent = sd)
    elif dist_class == 'SizeDist_LS':
        return OpticalProperties_VP(out, parent= sd)
    return out


def hemispheric_backscattering(osf_df):
    """scattering into backwards hemisphere from angulare scattering intensity

    Parameters
    ----------
    osf_df: pandas DataFrame
        This contains the angulare scattering intensity with column names giving the
        angles in radiant


    Returns
    -------
    pandas data frame with the scattering intensities
    """
    import pdb
    # pdb.set_trace()
    def ang_scat_funk2bs(index,ol):
        x = index #_np.deg2rad(index)
        f = ol
        # pdb.set_trace()
        # my phase function goes all the way to two py
        f = f[x < _np.pi]
        x = x[x < _np.pi]
        f_b = f[x >= _np.pi / 2.]
        x_b = x[x >= _np.pi / 2.]
        # pdb.set_trace()
        res_b = 2 * _np.pi * _integrate.simps(f_b * _np.sin(x_b), x_b)
        return res_b

    bs = _np.zeros(osf_df.shape[0])
    index = osf_df.columns
    for i in range(osf_df.shape[0]):
        ol = osf_df.iloc[i,:].values
        bs[i] = ang_scat_funk2bs(index,ol)
    bs = _pd.DataFrame(bs, index = osf_df.index)
    return bs

def hemispheric_forwardscattering(osf_df):
    """scattering into forward hemisphere from angulare scattering intensity

    Parameters
    ----------
    osf_df: pandas DataFrame
        This contains the angulare scattering intensity with column names giving the
        angles in radiant

    Returns
    -------
    pandas data frame with the scattering intensities
    """

    def ang_scat_funk2fs(index,ol):
        x = index #ol.index.values
        f = ol

        # my phase function goes all the way to two py
        f = f[x < _np.pi]
        x = x[x < _np.pi]
        f_f = f[x < _np.pi / 2.]
        x_f = x[x < _np.pi / 2.]

        res_f = 2 * _np.pi * _integrate.simps(f_f * _np.sin(x_f), x_f)
        return res_f

    fs = _np.zeros(osf_df.shape[0])
    index = osf_df.columns
    for i in range(osf_df.shape[0]):
        ol = osf_df.iloc[i,:].values
        fs[i] = ang_scat_funk2fs(index,ol)
    fs = _pd.DataFrame(fs, index = osf_df.index)
    return fs



#Todo: bins are redundand
# Todo: some functions should be switched of
# todo: right now this for layer and time series, not ok
class OpticalProperties(object):
    def __init__(self, parent):
        self._parent_sizedist = parent
        self.parameters = _sizedistribution._Parameters4Reductions_opt_prop(parent)

        # self.asymmetry_param = data['asymmetry_param']

        self._extinction_coeff = None
        self._scattering_coeff = None
        self._absorption_coeff = None

        self._hemispheric_backscattering = None
        # self._hemispheric_backscattering_ratio = None
        self._hemispheric_forwardscattering = None
        # self._hemispheric_forwardscattering_ratio = None

        self._optical_porperties_pv = None


        self.mean_effective_diameter = None
        self._parent_type = type(parent).__name__
        self.bins = parent.bins
        self.binwidth = parent.binwidth
        self.distributionType = parent.distributionType
        # self._data_period = self.parent_sizedist._data_period


    # @property
    # def mean_effective_diameter(self):
    #     if not self.__mean_effective_diameter:


    # # todo: remove
    # @property
    # def extinction_coeff_sum_along_d(self):
    #     _warnings.warn('extinction_coeff_sum_along_d is deprecated and will be removed in future versions. Use extingction_coeff instead')
    #     if not _np.any(self.__extinction_coeff_sum_along_d):
    #         data = self.extinction_coeff_per_bin.data.sum(axis = 1)
    #         df = _pd.DataFrame()
    #         df['ext_coeff_m^1'] = data
    #         if self._parent_type == 'SizeDist_TS':
    #             self.__extinction_coeff_sum_along_d = _timeseries.TimeSeries(df)
    #         elif self._parent_type == 'SizeDist':
    #             self.__extinction_coeff_sum_along_d = df
    #         else:
    #             raise TypeError('not possible for this distribution type')
    #         self.__extinction_coeff_sum_along_d._data_period = self._data_period
    #     return self.__extinction_coeff_sum_along_d
    #
    # # todo: remove
    # @extinction_coeff_sum_along_d.setter
    # def extinction_coeff_sum_along_d(self, data):
    #     self.__extinction_coeff_sum_along_d = data

    @property
    def extinction_coeff_per_bin(self):
        self._optical_porperties
        return self._extinction_coeff_per_bin

    @property
    def scattering_coeff_per_bin(self):
        self._optical_porperties
        return self._scattering_coeff_per_bin

    @property
    def absorption_coeff_per_bin(self):
        self._optical_porperties
        return self._absorption_coeff_per_bin

    @property
    def angular_scatt_func(self):
        self._optical_porperties
        return self._angular_scatt_func

    @property
    def _optical_porperties(self):
        if not self._optical_porperties_pv:
            data = size_dist2optical_properties(self, self._parent_sizedist)
            self._optical_porperties_pv = data

            ####
            self._extinction_coeff_per_bin = data['extCoeff_perrow_perbin']
            self._extinction_coeff = _pd.DataFrame(self._extinction_coeff_per_bin.sum(axis=1), columns=['ext_coeff_m^1'])

            ####
            self._scattering_coeff_per_bin = data['scattCoeff_perrow_perbin']
            self._scattering_coeff = _pd.DataFrame(self._scattering_coeff_per_bin.sum(axis=1), columns=['scatt_coeff_m^1'])

            #####
            self._absorption_coeff_per_bin = data['absCoeff_perrow_perbin']
            self._absorption_coeff = _pd.DataFrame(self._absorption_coeff_per_bin.sum(axis=1), columns=['abs_coeff_m^1'])
            ####
            self._angular_scatt_func = data['angular_scatt_func']
        return self._optical_porperties_pv

    # @property
    # def extinction_coeff(self):
    #     self._optical_porperties
    #     if not _np.any(self._extinction_coeff_sum_along_d):
    #         data = self.extinction_coeff_per_bin.sum(axis=1)
    #         df = _pd.DataFrame()
    #         df['ext_coeff_m^1'] = data
    #         if self._parent_type == 'SizeDist_TS':
    #             self._extinction_coeff_sum_along_d = _timeseries.TimeSeries(df)
    #             self._extinction_coeff_sum_along_d._data_period = self._data_period
    #         elif self._parent_type == 'SizeDist_LS':
    #             self._extinction_coeff_sum_along_d = _vertical_profile.VerticalProfile(df)
    #         elif self._parent_type == 'SizeDist':
    #             self._extinction_coeff_sum_along_d = df
    #         else:
    #             raise TypeError('not possible for this distribution type')
    #     return self._extinction_coeff_sum_along_d

    # @extinction_coeff.setter
    # def extinction_coeff(self, data):
    #     self._extinction_coeff_sum_along_d = data

    # @property
    # def scattering_coeff(self):
    #     if not _np.any(self._scattering_coeff_sum_along_d):
    #         data = self.scattering_coeff_per_bin.sum(axis=1)
    #         df = _pd.DataFrame()
    #         df['scatt_coeff_m^1'] = data
    #         if self._parent_type == 'SizeDist_TS':
    #             self._scattering_coeff_sum_along_d = _timeseries.TimeSeries(df)
    #         elif self._parent_type == 'SizeDist':
    #             self._scattering_coeff_sum_along_d = df
    #         else:
    #             raise TypeError('not possible for this distribution type')
    #         self._scattering_coeff_sum_along_d._data_period = self._data_period
    #     return self._scattering_coeff_sum_along_d

    # @scattering_coeff.setter
    # def scattering_coeff(self, data):
    #     self._scattering_coeff_sum_along_d = data


    @property
    def absorption_coeff(self):
        self._optical_porperties
        return self._absorption_coeff

    @property
    def extinction_coeff(self):
        self._optical_porperties
        return self._extinction_coeff

    @property
    def scattering_coeff(self):
        self._optical_porperties
        return self._scattering_coeff

    # @absorption_coeff.setter
    # def absorption_coeff(self, data):
    #     self.__absorption_coeff_sum_along_d = data


    @property
    def hemispheric_backscattering(self):
        if not _np.any(self._hemispheric_backscattering):
            self._hemispheric_backscattering = hemispheric_backscattering(self.angular_scatt_func)
            self._hemispheric_backscattering_ratio = _pd.DataFrame(
                self._hemispheric_backscattering.iloc[:, 0] / self._scattering_coeff.iloc[:, 0],
                columns=['hem_back_scatt_ratio'])
        return self._hemispheric_backscattering

    @property
    def hemispheric_backscattering_ratio(self):
        self.hemispheric_backscattering
        # if not _np.any(self._hemispheric_backscattering_ratio):
        #     self._hemispheric_backscattering_ratio = _pd.DataFrame(self.hemispheric_backscattering.iloc[:,0] / self._scattering_coeff.iloc[:,0], columns=['hem_beck_scatt_ratio'])
        return self._hemispheric_backscattering_ratio

    @property
    def hemispheric_forwardscattering(self):
        if not _np.any(self._hemispheric_forwardscattering):
            self._hemispheric_forwardscattering = hemispheric_forwardscattering(self.angular_scatt_func)
            self._hemispheric_forwardscattering_ratio = _pd.DataFrame(self._hemispheric_forwardscattering.iloc[:, 0] /  self._scattering_coeff.iloc[:, 0],
                columns=['hem_forward_scatt_ratio'])
        return self._hemispheric_forwardscattering

    @property
    def hemispheric_forwardscattering_ratio(self):
        self.hemispheric_forwardscattering
        # if not _np.any(self._hemispheric_forwardscattering_ratio):
        #     self._hemispheric_forwardscattering_ratio = self.hemispheric_forwardscattering / self.scattering_coeff
        return self._hemispheric_forwardscattering_ratio

    def convert_between_moments(self, moment, verbose = False):
        return _sizedist_moment_conversion.convert(self,moment, verbose = verbose)

    def copy(self):
        return _deepcopy(self)




#Todo: bins are redundand
# Todo: some functions should be switched of
# todo: right now this for layer and time series, not ok
class DEPRECATEDOpticalProperties(object):
    def __init__(self, data, parent = None):
        self.parent_sizedist = parent

        self.data_orig = data
        self.wavelength =  data['wavelength']
        self.index_of_refraction = data['index_of_refraction']
        self.extinction_coeff_per_bin = data['extCoeff_perrow_perbin']
        self.scattering_coeff_per_bin = data['scattCoeff_perrow_perbin']
        self.absorption_coeff_per_bin = data['absCoeff_perrow_perbin']
        self.angular_scatt_func = data['angular_scatt_func']

        # self.asymmetry_param = data['asymmetry_param']

        self.__extinction_coeff_sum_along_d = None
        self.__scattering_coeff_sum_along_d = None
        self.__absorption_coeff_sum_along_d = None


        self.mean_effective_diameter = None
        self._parent_type = data['parent_type']
        self.bins = data['bins']
        self.binwidth = data['binwidth']
        self.distributionType = data['distType']
        # self._data_period = self.parent_sizedist._data_period


    # @property
    # def mean_effective_diameter(self):
    #     if not self.__mean_effective_diameter:


    # # todo: remove
    # @property
    # def extinction_coeff_sum_along_d(self):
    #     _warnings.warn('extinction_coeff_sum_along_d is deprecated and will be removed in future versions. Use extingction_coeff instead')
    #     if not _np.any(self.__extinction_coeff_sum_along_d):
    #         data = self.extinction_coeff_per_bin.data.sum(axis = 1)
    #         df = _pd.DataFrame()
    #         df['ext_coeff_m^1'] = data
    #         if self._parent_type == 'SizeDist_TS':
    #             self.__extinction_coeff_sum_along_d = _timeseries.TimeSeries(df)
    #         elif self._parent_type == 'SizeDist':
    #             self.__extinction_coeff_sum_along_d = df
    #         else:
    #             raise TypeError('not possible for this distribution type')
    #         self.__extinction_coeff_sum_along_d._data_period = self._data_period
    #     return self.__extinction_coeff_sum_along_d
    #
    # # todo: remove
    # @extinction_coeff_sum_along_d.setter
    # def extinction_coeff_sum_along_d(self, data):
    #     self.__extinction_coeff_sum_along_d = data

    @property
    def extinction_coeff(self):
        if not _np.any(self.__extinction_coeff_sum_along_d):
            data = self.extinction_coeff_per_bin.data.sum(axis=1)
            df = _pd.DataFrame()
            df['ext_coeff_m^1'] = data
            if self._parent_type == 'SizeDist_TS':
                self.__extinction_coeff_sum_along_d = _timeseries.TimeSeries(df)
                self.__extinction_coeff_sum_along_d._data_period = self._data_period
            elif self._parent_type == 'SizeDist_LS':
                self.__extinction_coeff_sum_along_d = _vertical_profile.VerticalProfile(df)
            elif self._parent_type == 'SizeDist':
                self.__extinction_coeff_sum_along_d = df
            else:
                raise TypeError('not possible for this distribution type')
        return self.__extinction_coeff_sum_along_d

    @extinction_coeff.setter
    def extinction_coeff(self, data):
        self.__extinction_coeff_sum_along_d = data

    @property
    def scattering_coeff(self):
        if not _np.any(self.__scattering_coeff_sum_along_d):
            data = self.scattering_coeff_per_bin.data.sum(axis=1)
            df = _pd.DataFrame()
            df['scatt_coeff_m^1'] = data
            if self._parent_type == 'SizeDist_TS':
                self.__scattering_coeff_sum_along_d = _timeseries.TimeSeries(df)
            elif self._parent_type == 'SizeDist':
                self.__scattering_coeff_sum_along_d = df
            else:
                raise TypeError('not possible for this distribution type')
            self.__scattering_coeff_sum_along_d._data_period = self._data_period
        return self.__scattering_coeff_sum_along_d

    @scattering_coeff.setter
    def scattering_coeff(self, data):
        self.__scattering_coeff_sum_along_d = data



    @property
    def absorption_coeff(self):
        if not _np.any(self.__absorption_coeff_sum_along_d):
            data = self.absorption_coeff_per_bin.data.sum(axis=1)
            df = _pd.DataFrame()
            df['abs_coeff_m^1'] = data
            if self._parent_type == 'SizeDist_TS':
                self.__absorption_coeff_sum_along_d = _timeseries.TimeSeries(df)
            elif self._parent_type == 'SizeDist':
                self.__absorption_coeff_sum_along_d = df
            else:
                raise TypeError('not possible for this distribution type')
            self.__absorption_coeff_sum_along_d._data_period = self._data_period
        return self.__absorption_coeff_sum_along_d

    @absorption_coeff.setter
    def absorption_coeff(self, data):
        self.__absorption_coeff_sum_along_d = data


    @property
    def hemispheric_backscattering(self):
        if not self.__hemispheric_backscattering:
            self.__hemispheric_backscattering = hemispheric_backscattering(self.angular_scatt_func)
        return self.__hemispheric_backscattering

    @property
    def hemispheric_forwardscattering(self):
        if not self.__hemispheric_forwardscattering:
            self.__hemispheric_forwardscattering = hemispheric_forwardscattering(self.angular_scatt_func)
        return self.__hemispheric_forwardscattering

    @property
    def hemispheric_backscattering_ratio(self):
        if not self.__hemispheric_backscattering_ratio:
            self.__hemispheric_backscattering_ratio = self.hemispheric_backscattering / self.scattering_coeff
        return self.__hemispheric_backscattering_ratio

    @property
    def hemispheric_forwardscattering_ratio(self):
        if not self.hemispheric_forwardscattering_ratio:
            self.__hemispheric_forwardscattering_ratio = self.hemispheric_forwardscattering / self.scattering_coeff
        return self.__hemispheric_forwardscattering_ratio

    def convert_between_moments(self, moment, verbose = False):
        return _sizedist_moment_conversion.convert(self,moment, verbose = verbose)

    def copy(self):
        return _deepcopy(self)



class OpticalProperties_TS(OpticalProperties):

    @property
    def hemispheric_forwardscattering(self):
        super().hemispheric_forwardscattering
        return _timeseries.TimeSeries(self._hemispheric_forwardscattering, sampling_period = self._parent_sizedist._data_period)

    @property
    def hemispheric_backscattering(self):
        super().hemispheric_backscattering
        return _timeseries.TimeSeries(self._hemispheric_backscattering, sampling_period = self._parent_sizedist._data_period)

    @property
    def hemispheric_backscattering_ratio(self):
        self.hemispheric_backscattering
        return _timeseries.TimeSeries(self._hemispheric_backscattering_ratio, sampling_period = self._parent_sizedist._data_period)

    @property
    def hemispheric_forwardscattering_ratio(self):
        self.hemispheric_forwardscattering
        return _timeseries.TimeSeries(self._hemispheric_forwardscattering_ratio, sampling_period = self._parent_sizedist._data_period)

    @property
    def absorption_coeff(self):
        self._optical_porperties
        return _timeseries.TimeSeries(self._absorption_coeff, sampling_period = self._parent_sizedist._data_period)

    @property
    def extinction_coeff(self):
        self._optical_porperties
        return _timeseries.TimeSeries(self._extinction_coeff, sampling_period = self._parent_sizedist._data_period)

    @property
    def scattering_coeff(self):
        self._optical_porperties
        return _timeseries.TimeSeries(self._scattering_coeff, sampling_period = self._parent_sizedist._data_period)

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.extinction_coeff_per_bin = _timeseries.TimeSeries_2D(self.extinction_coeff_per_bin)
    #     self.extinction_coeff_per_bin._data_period = self.parent_sizedist._data_period
    #
    #     self.scattering_coeff_per_bin = _timeseries.TimeSeries_2D(self.scattering_coeff_per_bin)
    #     self.scattering_coeff_per_bin._data_period = self.parent_sizedist._data_period
    #
    #     self.absorption_coeff_per_bin = _timeseries.TimeSeries_2D(self.absorption_coeff_per_bin)
    #     self.absorption_coeff_per_bin._data_period = self.parent_sizedist._data_period
    #
    #     self.angular_scatt_func = _timeseries.TimeSeries_2D(self.angular_scatt_func.transpose())
    #     self.angular_scatt_func._data_period = self.parent_sizedist._data_period
    #
    #     self.__hemispheric_forwardscattering = None
    #     self.__hemispheric_backscattering = None
    #     self.__hemispheric_backscattering_ratio = None
    #     self.__hemispheric_forwardscattering_ratio = None
    #     self._data_period = self.parent_sizedist._data_period
    #
    #
    #
    # @property
    # def hemispheric_backscattering(self):
    #     if not self.__hemispheric_backscattering:
    #         out = hemispheric_backscattering(self.angular_scatt_func.data)
    #         out = _timeseries.TimeSeries(out)
    #         out._data_period = self.angular_scatt_func._data_period
    #         self.__hemispheric_backscattering = out
    #     return self.__hemispheric_backscattering
    #
    # @hemispheric_backscattering.setter
    # def hemispheric_backscattering(self,value):
    #     self.__hemispheric_backscattering = value
    #
    # @property
    # def hemispheric_forwardscattering(self):
    #     if not self.__hemispheric_forwardscattering:
    #         out = hemispheric_forwardscattering(self.angular_scatt_func.data)
    #         out = _timeseries.TimeSeries(out)
    #         out._data_period = self.angular_scatt_func._data_period
    #         self.__hemispheric_forwardscattering = out
    #     return self.__hemispheric_forwardscattering
    #
    #
    # @hemispheric_forwardscattering.setter
    # def hemispheric_forwardscattering(self, value):
    #     self.__hemispheric_forwardscattering = value
    #
    # @property
    # def hemispheric_backscattering_ratio(self):
    #     """ratio between backscattering and overall scattering"""
    #     if not self.__hemispheric_backscattering_ratio:
    #         # self.__hemispheric_backscattering_ratio = self.hemispheric_backscattering / self.extinction_coeff
    #         self.__hemispheric_backscattering_ratio = self.hemispheric_backscattering / self.scattering_coeff
    #     return self.__hemispheric_backscattering_ratio
    #
    # @property
    # def hemispheric_forwardscattering_ratio(self):
    #     """ratio between forwardscattering and over scattering"""
    #     if not self.__hemispheric_forwardscattering_ratio:
    #         self.__hemispheric_forwardscattering_ratio = self.hemispheric_forwardscattering / self.scattering_coeff
    #     return self.__hemispheric_forwardscattering_ratio


class OpticalProperties_VP(OpticalProperties):

    @property
    def hemispheric_forwardscattering(self):
        super().hemispheric_forwardscattering
        return _vertical_profile.VerticalProfile(self._hemispheric_forwardscattering)

    @property
    def hemispheric_backscattering(self):
        super().hemispheric_backscattering
        return _vertical_profile.VerticalProfile(self._hemispheric_backscattering)

    @property
    def hemispheric_backscattering_ratio(self):
        self.hemispheric_backscattering
        return _vertical_profile.VerticalProfile(self._hemispheric_backscattering_ratio)

    @property
    def hemispheric_forwardscattering_ratio(self):
        self.hemispheric_forwardscattering
        return _vertical_profile.VerticalProfile(self._hemispheric_forwardscattering_ratio)

    @property
    def absorption_coeff(self):
        self._optical_porperties
        return _vertical_profile.VerticalProfile(self._absorption_coeff)

    @property
    def extinction_coeff(self):
        self._optical_porperties
        return _vertical_profile.VerticalProfile(self._extinction_coeff)

    @property
    def scattering_coeff(self):
        self._optical_porperties
        return _vertical_profile.VerticalProfile(self._scattering_coeff)

    @property
    def _optical_porperties(self):
        if not self._optical_porperties_pv:
            super()._optical_porperties
            layerthickness = self._parent_sizedist.layerbounderies[:, 1] - self._parent_sizedist.layerbounderies[:, 0]
            aod_per_bin_per_layer = self._parent_sizedist.optical_properties.extinction_coeff_per_bin.multiply(layerthickness, axis=0)
            aod_per_layer = _pd.DataFrame(aod_per_bin_per_layer.sum(axis=1), columns=['aod_per_layer'])
            self._aod = aod_per_layer.values.sum()
            aod_cumulative = aod_per_layer.iloc[::-1].cumsum()
            aod_cumulative.rename(columns={'aod_per_layer': 'aod'}, inplace=True)
            self._aod_cumulative = aod_cumulative
        return self._optical_porperties_pv

    @property
    def aod(self):
        self._optical_porperties
        return self._aod

    @property
    def aod_cumulative(self):
        self._optical_porperties
        return _vertical_profile.VerticalProfile(self._aod_cumulative)

class DEPRECATED_OpticalProperties_VP(OpticalProperties):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extinction_coeff_per_bin = _vertical_profile.VerticalProfile_2D(self.extinction_coeff_per_bin)
        self.aerosol_optical_depth_cumulative_VP = _vertical_profile.VerticalProfile(self._data_dict['AOD_cum'])
        self.asymmetry_param_VP = _vertical_profile.VerticalProfile(self._data_dict['asymmetry_param'])
        self.aerosol_optical_depth_cumulative = self._data_dict['AOD']

class ExtinctionCoeffVerticlProfile(_vertical_profile.VerticalProfile):
    def __init__(self, ext, parent, wavelength, index_of_refraction):
        super(ExtinctionCoeffVerticlProfile, self).__init__(ext)
        self.parent = parent
        self.wavelength = wavelength
        self.index_of_refraction = index_of_refraction

    def plot(self, *args, **kwargs):
        a = super(ExtinctionCoeffVerticlProfile, self).plot(*args, **kwargs)
        a.set_xlabel('Extinction coefficient (m$^{-1}$)')
        return a


def _perform_Miecalculations(diam, wavelength, n, noOfAngles=100.):
    """
    Performs Mie calculations

    Parameters
    ----------
    diam:       NumPy array of floats
                Array of diameters over which to perform Mie calculations; units are um
    wavelength: float
                Wavelength of light in um for which to perform calculations
    n:          complex
                Ensemble complex index of refraction

    Returns
        panda DataTable with the diameters as the index and the mie_scattering results in the different collumns
        total_extinction_coefficient: this takes the sum of all particles crossections of the particular diameter in a qubic
                                      meter. This is in principle the AOD of an L

    """


    diam = _np.asarray(diam)

    extinction_efficiency = _np.zeros(diam.shape)
    scattering_efficiency = _np.zeros(diam.shape)
    absorption_efficiency = _np.zeros(diam.shape)

    extinction_crossection = _np.zeros(diam.shape)
    scattering_crossection = _np.zeros(diam.shape)
    absorption_crossection = _np.zeros(diam.shape)

    # phase_function_natural = pd.DataFrame()
    angular_scattering_natural = _pd.DataFrame()
    # extinction_coefficient = np.zeros(diam.shape)
    # scattering_coefficient = np.zeros(diam.shape)
    # absorption_coefficient = np.zeros(diam.shape)



    # Function for calculating the size parameter for wavelength l and radius r
    sp = lambda r, l: 2. * _np.pi * r / l
    for e, d in enumerate(diam):
        radius = d / 2.

        # print('sp(radius, wavelength)', sp(radius, wavelength))
        # print('n', n)
        # print('d', d)

        mie = _bhmie.bhmie_hagen(sp(radius, wavelength), n, noOfAngles, diameter=d)
        values = mie.return_Values_as_dict()
        extinction_efficiency[e] = values['extinction_efficiency']

        # print("values['extinction_crosssection']",values['extinction_crosssection'])


        scattering_efficiency[e] = values['scattering_efficiency']
        absorption_efficiency[e] = values['extinction_efficiency'] - values['scattering_efficiency']

        extinction_crossection[e] = values['extinction_crosssection']
        scattering_crossection[e] = values['scattering_crosssection']
        absorption_crossection[e] = values['extinction_crosssection'] - values['scattering_crosssection']

        # phase_function_natural[d] = values['phaseFct_natural']['Phase_function_natural'].values
        angular_scattering_natural[d] = mie.get_angular_scatt_func().natural.values

        # print('\n')

    # phase_function_natural.index = values['phaseFct_natural'].index
    angular_scattering_natural.index = mie.get_angular_scatt_func().index

    out = _pd.DataFrame(index=diam)
    out['extinction_efficiency'] = _pd.Series(extinction_efficiency, index=diam)
    out['scattering_efficiency'] = _pd.Series(scattering_efficiency, index=diam)
    out['absorption_efficiency'] = _pd.Series(absorption_efficiency, index=diam)

    out['extinction_crossection'] = _pd.Series(extinction_crossection, index=diam)
    out['scattering_crossection'] = _pd.Series(scattering_crossection, index=diam)
    out['absorption_crossection'] = _pd.Series(absorption_crossection, index=diam)
    return out, angular_scattering_natural


def _get_coefficients(crossection, cn):
    """
    Calculates the extinction, scattering or absorbtion coefficient

    Parameters
    ----------
    crosssection:   float
                    Units are um^2
    cn:             float
                    Particle concentration in cc^-1

    Returns
    --------
    coefficient in m^-1.  This is the differential AOD.
    """
    crossection = crossection.copy()
    cn = cn.copy()
    crossection *= 1e-12  # conversion from um^2 to m^2
    cn *= 1e6  # conversion from cm^-3 to m^-3
    coefficient = cn * crossection

    # print('cn',cn)
    # print('crossection', crossection)
    # print('coeff',coefficient)
    # print('\n')

    return coefficient

def vertical_profile2accumulative_AOD(timeseries):
    data = timeseries.data.copy()
    data.dropna(inplace = True)
    accu_aod = _np.zeros(data.shape)
    for col,k in enumerate(data.keys()):
        series = data[k]
        # series.dropna(inplace = True)
        y = series.values*1e-6
        x = series.index.values

        x = x[::-1]
        y = y[::-1]


        st = 0
        # for e,i in enumerate(x):
        for e in range(x.shape[0]):
            end = e+1
            accu_aod[e][col] = -_integrate.simps(y[st:end], x[st:end])

    accu_aod = _pd.DataFrame(accu_aod, index = x, columns=data.keys())
    accu_aod = _vertical_profile.VerticalProfile(accu_aod)

    accu_aod._x_label = 'AOD$_{abs}$'
    return accu_aod