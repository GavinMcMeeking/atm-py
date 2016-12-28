from unittest import TestCase
import numpy as np
import pandas as pd
import os
test_data_folder = os.path.join(os.path.dirname(__file__), 'test_data/')
# print(test_data_folder)
# test_data_folder = './test_data/'
#### data archives
######## ARM
from atmPy.data_archives.arm import _read_data
import atmPy
from atmPy.aerosols import size_distribution
from atmPy.data_archives import arm
from atmPy.aerosols.physics import hygroscopic_growth as hyg
from atmPy.general import vertical_profile

class ArmDataTests(TestCase):
    def test_1twr10xC1(self):
        out = _read_data.read_cdf(test_data_folder, data_product='1twr10xC1')
        out = out['1twr10xC1']

        # rh
        soll = pd.read_csv(test_data_folder + '1twr10xC1_rh.csv', index_col=0,
                           dtype={'rh_25m': np.float32, 'rh_60m': np.float32}
                           )

        ## index
        self.assertLess(abs((out.relative_humidity.data.index.values - pd.to_datetime(soll.index).values).sum() / np.timedelta64(1, 's')), 1e-10)
        # self.assertTrue(np.all(out.relative_humidity.data.index.values == pd.to_datetime(soll.index).values))

        ## rest
        soll.columns.name = out.relative_humidity.data.columns.name
        # self.assertTrue(np.all(out.relative_humidity.data.values == soll.values))
        self.assertLess(abs((out.relative_humidity.data.values - soll.values).sum()), 1e-2)
        # temp
        soll = pd.read_csv(test_data_folder + '1twr10xC1_temp.csv', index_col=0,
                           dtype={'temp_25m': np.float32, 'temp_60m': np.float32}
                           )
        soll.columns.name = out.temperature.data.columns.name
        # self.assertTrue(np.all(out.temperature.data.values == soll.values))
        self.assertLess(abs((out.temperature.data.values - soll.values).sum()), 1e-2)

        # vapor pressure
        soll = pd.read_csv(test_data_folder + '1twr10xC1_p_vapor.csv', index_col=0,
                           dtype={'vap_pres_25m': np.float32, 'vap_pres_60m': np.float32}
                           )
        soll.columns.name = out.vapor_pressure.data.columns.name
        # self.assertTrue(np.all(out.vapor_pressure.data.values == soll.values))
        self.assertLess(abs((out.vapor_pressure.data.values - soll.values).sum()), 1e-2)


class SizeDistTest(TestCase):
    def test_concentrations(self):
        sd = size_distribution.sizedistribution.simulate_sizedistribution(diameter=[15, 3000],
                                                                          numberOfDiameters=50,
                                                                          centerOfAerosolMode=222,
                                                                          widthOfAerosolMode=0.18,
                                                                          numberOfParticsInMode=888)

        self.assertEqual(round(sd.particle_number_concentration, 4) , round(888.0, 4))
        self.assertEqual(round(float(sd.particle_surface_concentration.values), 4) , round(194.42186363605904, 4))
        self.assertEqual(round(float(sd.particle_volume_concentration.values), 4) , round(11.068545094055812, 4))

        sd.parameters4reductions.particle_density = 2.2
        self.assertEqual(round(float(sd.particle_mass_concentration), 4), round(24.350799206922783, 4))


    def test_mixing_ratios(self):
        sd = size_distribution.sizedistribution.simulate_sizedistribution_timeseries(diameter=[15, 3000],
                                                                                     numberOfDiameters=50,
                                                                                     centerOfAerosolMode=222,
                                                                                     widthOfAerosolMode=0.18,
                                                                                     numberOfParticsInMode=888,
                                                                                     startDate='2015-10-23 16:00:00',
                                                                                     endDate='2015-10-23 17:00:00',
                                                                                     frequency=60)

        sd.data = sd.data.iloc[[0], :]
        sd.housekeeping = atmPy.general.timeseries.TimeSeries(
            pd.DataFrame(np.array([[250.], [750.]]).transpose(), index=sd.data.index,
                         columns=['temperature_K', 'pressure_Pa']))
        sd.parameters4reductions.particle_density = 2.8

        self.assertEqual(round(float(sd.particle_mass_mixing_ratio.data.values) * 1e6, 4), round(2.96533739732464, 4))

    def test_moment_conversion(self):
        sd = size_distribution.sizedistribution.simulate_sizedistribution(diameter=[15, 3000],
                                                                          numberOfDiameters=50,
                                                                          centerOfAerosolMode=222,
                                                                          widthOfAerosolMode=0.18,
                                                                          numberOfParticsInMode=888)

        sd_dNdDp = sd.convert2dNdDp()
        sd_dNdlogDp = sd.convert2dNdlogDp()
        sd_dSdDp = sd.convert2dSdDp()
        sd_dSdlogDp = sd.convert2dSdlogDp()
        sd_dVdDp = sd.convert2dVdDp()
        sd_dVdlogDp = sd.convert2dVdlogDp()

        folder = test_data_folder

        # sd.save_csv(folder + 'aerosols_size_dist_moments_sd.nc')
        # sd_dNdDp.save_csv(folder + 'aerosols_size_dist_moments_sd_dNdDp.nc')
        # sd_dNdlogDp.save_csv(folder + 'aerosols_size_dist_moments_sd_dNdlogDp.nc')
        # sd_dSdDp.save_csv(folder + 'aerosols_size_dist_moments_sd_dSdDp.nc')
        # sd_dSdlogDp.save_csv(folder + 'aerosols_size_dist_moments_sd_dSdlogDp.nc')
        # sd_dVdDp.save_csv(folder + 'aerosols_size_dist_moments_sd_dVdDp.nc')
        # sd_dVdlogDp.save_csv(folder + 'aerosols_size_dist_moments_sd_dVdlogDp.nc')

        sd_soll = size_distribution.sizedistribution.read_csv(folder + 'aerosols_size_dist_moments_sd.nc')
        sd_dNdDp_soll = size_distribution.sizedistribution.read_csv(folder + 'aerosols_size_dist_moments_sd_dNdDp.nc')
        sd_dNdlogDp_soll = size_distribution.sizedistribution.read_csv(folder + 'aerosols_size_dist_moments_sd_dNdlogDp.nc')
        sd_dSdDp_soll = size_distribution.sizedistribution.read_csv(folder + 'aerosols_size_dist_moments_sd_dSdDp.nc')
        sd_dSdlogDp_soll = size_distribution.sizedistribution.read_csv(folder + 'aerosols_size_dist_moments_sd_dSdlogDp.nc')
        sd_dVdDp_soll = size_distribution.sizedistribution.read_csv(folder + 'aerosols_size_dist_moments_sd_dVdDp.nc')
        sd_dVdlogDp_soll = size_distribution.sizedistribution.read_csv(folder + 'aerosols_size_dist_moments_sd_dVdlogDp.nc')

        threshold = 1e-10
        msg = '\nthreshold: {}\nisnan: {}\nisnotnan: {}'.format((sd.data.values.max() * threshold),
                                                 np.isnan(sd.data.values - sd_soll.data.values).sum(),
                                                 (~np.isnan(sd.data.values - sd_soll.data.values)).sum())
        self.assertLess(abs((sd.data.values - sd_soll.data.values)).sum() , (sd.data.values.max() * threshold), msg = msg)
        self.assertLess(abs((sd_dNdDp.data.values - sd_dNdDp_soll.data.values)).sum() , (sd_dNdDp.data.values.max() * threshold))
        self.assertLess(abs((sd_dSdDp.data.values - sd_dSdDp_soll.data.values)).sum() , (sd_dSdDp.data.values.max() * threshold))
        self.assertLess(abs((sd_dVdDp.data.values - sd_dVdDp_soll.data.values)).sum() , (sd_dVdDp.data.values.max() * threshold))
        self.assertLess(abs((sd_dNdlogDp.data.values - sd_dNdlogDp_soll.data.values)).sum() , (sd_dNdlogDp.data.values.max() * threshold))
        self.assertLess(abs((sd_dSdlogDp.data.values - sd_dSdlogDp_soll.data.values)).sum() , (sd_dSdlogDp.data.values.max() * threshold))
        self.assertLess(abs((sd_dVdlogDp.data.values - sd_dVdlogDp_soll.data.values)).sum() , (sd_dVdlogDp.data.values.max() * threshold))

    def test_opt_prop_LS(self):
        sd = size_distribution.sizedistribution.simulate_sizedistribution_layerseries(diameter=[10, 2500],
                                                                                      numberOfDiameters=100,
                                                                                      heightlimits=[0, 6000],
                                                                                      noOflayers=100,
                                                                                      layerHeight=[500.0, 4000.0],
                                                                                      layerThickness=[100.0, 300.0],
                                                                                      layerDensity=[1000.0, 50.0],
                                                                                      layerModecenter=[200.0, 800.0],
                                                                                      widthOfAerosolMode=0.2)

        sd.optical_properties.parameters.refractive_index = 1.56
        sd.optical_properties.parameters.wavelength = 515

        fname = os.path.join(test_data_folder, 'aerosols_size_dist_LS_optprop.nc')
        sdl = atmPy.read_file.netCDF(fname)

        self.sizedistributionLS = sd

        # self.assertTrue(np.all(sd.optical_properties.aerosol_optical_depth_cumulative_VP.data.values == sdl.data.values))
        self.assertLess(abs((sd.optical_properties.aod_cumulative.data.values - sdl.data.values).sum()), 1e-10)

    def test_growth_opt_propLS(self):

        # use the same dist_LS as in test_opt_prop_LS
        sdto = SizeDistTest()
        sdto.test_opt_prop_LS()

        # generate some RH which we can put into the housekeeping
        hk = pd.DataFrame(index=sdto.sizedistributionLS.data.index, columns=['Relative_humidity'])
        hk['Relative_humidity'] = 90
        hk = vertical_profile.VerticalProfile(hk)
        sdto.sizedistributionLS.housekeeping = hk

        # let it grow
        distg = sdto.sizedistributionLS.apply_hygro_growth(0.7)

        # load the test data
        fname = os.path.join(test_data_folder, 'aerosols_size_dist_LS_hyg_growth_optprop.nc')
        aodcs = atmPy.read_file.netCDF(fname)

        threshold = distg.optical_properties.aod_cumulative.data.values.sum() * 1e-10

        # res = np.abs(distg.optical_properties.aerosol_optical_depth_cumulative_VP.data.values
        #              - aodcs.data.values).sum() < threshold
        self.assertLess(np.abs(distg.optical_properties.aod_cumulative.data.values
                     - aodcs.data.values).sum(), threshold)



class PhysicsHygroscopicityTest(TestCase):
    def test_hygroscopic_growth_factor_distributions(self):
        fname = os.path.join(test_data_folder, 'sgptdmahygC1.b1.20120601.004227.cdf')
        out = arm.read_netCDF(fname, data_quality='patchy', leave_cdf_open=False)
        hgfd = hyg.HygroscopicGrowthFactorDistributions(out.hyg_distributions.data.loc[:, 200.0, :].transpose())
        # hgfd.plot()

        fname = os.path.join(test_data_folder, 'aerosols_physics_hygroscopicity_growth_mode.csv')
        growth_mode_soll = pd.read_csv(fname, index_col=0)

        threshold = growth_mode_soll.ratio.sum() * 1e-5
        self.assertLess(np.abs(hgfd.growth_modes.ratio - growth_mode_soll.ratio).sum(), threshold)

        threshold = growth_mode_soll.gf.sum() * 1e-7
        self.assertLess(np.abs(hgfd.growth_modes.gf - growth_mode_soll.gf).sum(), threshold)

        #######
        fname = os.path.join(test_data_folder, 'aerosols_physics_hygroscopicity_mixing_state.csv')
        mixing_state_soll = pd.read_csv(fname, index_col=0)

        threshold = mixing_state_soll.mixing_state.sum() * 1e-6
        self.assertLess(np.abs(hgfd.mixing_state.mixing_state - mixing_state_soll.mixing_state).sum(), threshold)