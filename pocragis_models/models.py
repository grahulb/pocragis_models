"""
This module contains all the components required to run
PoCRA's soil-moisture model. This model is a point-based simulation model,
in the sense that it represents the interplay, over time, of soil-moisture
with other water balance components at a given location (point, in GIS terms).
The model is based on four broad bio-physical entities:
1. Field: The field conditions at the location
2. Crop: Crop sown at the location, if any
3. Weather: The weather conditions at the location
4. Water: The water-components conceptualized by the soil-moisture model.
The module is structured in-line with this to have four corresponding classes.

Note: The processing of equations for model-simulation has been implemented
as static methods to allow their general-purpose (black-box) use not tied to
the corresponding class' structure, and yet allowing them
to be kept within the class' premises for clear conceptual design
that indicates the entity(modelled by its class) which that method simulates.

PoCRA's soil-moisture model has been customized from SWAT's models
and thus contains sub-models within it. Each of these sub-models generally
belongs to one of the four aforementioned bio-physical entities and thus
have been coded into their corresponding class. In particular,
1.	<Field> class includes the 'model' that determines the set-up of
	field properties with respect to soil-moisture.
2.	<Weather> class includes two models. One computes solar-radiation
	for a given latitude and a given day-of-year and the other computes
	reference evapotranspiration.
3. <Water> class includes two models. One computes potential evapotranspiration
	and the other computes all the water-components for the day(time-step).

Although all these models have been implemented as functions within the class,
they have been designated as static-methods and implemented such that their
results depend only on their input parameters and nothing else.
One major implication of this form of implementation is that anyone with
basic skills of writing arithmetic statements in python can modify the 
internals of the models easily without affecting other parts of the code.

(The user is assumed to know the models and meanings of the input-parameters.
Their documentation is available on IIT's PoCRA webpage.)

Finally, the <PocraSMModelSimulation> class provides an API to simulate
PoCRA's soil-moisture model over a duration of days(time-steps).
The siulation is done for as many days(time-steps) as the length of arrays
of the weather parameters (like rain) given as input to the class constructor.
See this class' documentation to know its API.
"""

import math

from . import lookups



class Field:
	"""
	Represents the field conditions at the modelled location.
	These field conditions currently include static properties like:
	1. Soil properties
	2. Land-Use-Land-Cover
	3. Terrain slope
	which are assumed to be static for the purpose of
	PoCRA's soil-moisture model.
	"""
	
	def __init__(s, soil_texture, soil_depth_category, lulc_type, slope, num_daily_phases):
		"""
		Set basic field properties
		Set derived field parameters required in the model
		"""

		s.soil_texture = soil_texture.lower()
		s.soil_depth_category = soil_depth_category.lower()
		s.lulc_type = lulc_type.lower()
		s.slope = slope


		#### Set parameters actually required in soil-moisture model. ####
		
		# Derived from lookups
		soil_texture_properties = lookups.dict_soil_properties[s.soil_texture]
		s.wp = soil_texture_properties['wp']
		s.fc = soil_texture_properties['fc']
		s.sat = soil_texture_properties['sat']
		s.ksat = soil_texture_properties['ksat']
		
		s.cn_val = lookups.dict_lulc_hsg_curveno[
			lookups.dict_lulc[s.lulc_type]
		][soil_texture_properties['hsg']]
		
		s.soil_depth = lookups.dict_soil_depth_category_to_value[s.soil_depth_category]

		# Derived by calculation
		field_setup = Field.pocra_sm_model_field_setup(
			s.wp, s.fc, s.sat, s.soil_depth, s.cn_val, s.slope, s.ksat, num_daily_phases
		)
		s.smax = field_setup['smax']
		s.w1 = field_setup['w1']
		s.w2 = field_setup['w2']
		s.perc_factor = field_setup['perc_factor']


	@staticmethod
	def pocra_sm_model_field_setup(wp, fc, sat, soil_depth, cn_val, slope, ksat, num_daily_phases):
		
		# some utility variables
		sat_minus_wp_depth = (sat-wp) * soil_depth * 1000
		fc_minus_wp_depth = (fc-wp) * soil_depth * 1000
		sat_minus_fc_depth = (sat-fc) * soil_depth * 1000

		# smax
		cn3 = cn_val * math.exp( 0.00673 * (100-cn_val) )
		if (slope > 5.0):
			cn_val = ( (
				((cn3 - cn_val) / 3) * ( 1 - 2 * math.exp(-13.86*slope*0.01) )
			) + cn_val )
		cn1_s = ( cn_val - 
			20 * (100-cn_val) / ( 100-cn_val + math.exp(2.533 - 0.0636*(100-cn_val)) )
		)
		cn3_s = cn_val * math.exp(0.00673*(100-cn_val))
		smax = 25.4 * (1000/cn1_s - 10)
		if smax == 0:
			raise Exception('smax is zero')
		
		# w2
		s3 = 25.4 * (1000/cn3_s - 10)
		w2 = ((
			math.log(fc_minus_wp_depth/(1-s3/smax) - fc_minus_wp_depth)
			- math.log (sat_minus_wp_depth/(1-2.54/smax) - sat_minus_wp_depth)
		) / (sat_minus_fc_depth) )

		# w1
		w1 = (
			math.log(fc_minus_wp_depth/(1- s3/smax) - fc_minus_wp_depth)
			+ w2 * fc_minus_wp_depth
		)

		# perc_factor
		TT_perc = sat_minus_fc_depth/ksat
		perc_factor = 1 - math.exp(-24 / num_daily_phases / TT_perc)

		return {
			'smax': smax,
			'w1': w1,
			'w2': w2,
			'perc_factor': perc_factor
		}



class Crop:
	"""
	Represents those properties of the crop or other vegetation at the
	modelled location, that play a role in simulating the model.
	"""
	
	def __init__(self, name):

		self.name = name

		if self.name in lookups.dict_of_properties_for_crop_and_croplike:
			crop_properties = lookups.dict_of_properties_for_crop_and_croplike[self.name]
		self.kc = crop_properties['kc']
		self.depletion_factor = crop_properties['depletion_factor']
		self.root_depth = crop_properties['root_depth']
		self.is_pseudo_crop = crop_properties['is_pseudo_crop']



class Weather:
	"""
	Represents the weather conditions including their determinants,
	at the modelled location and time,
	that play a role in simulating the model.
	"""
	
	G_sc = 0.082 # used in estimating R_a(radiation)
	t1 = 1 # length of time-step in hours(for hourly-model)
	k_Rs = 0.16
	alpha = 0.23
	sigma = 2.043 * 10**(-10)

	
	def __init__(self,
		rain, et0=None,
		temp_daily_min=None, temp_daily_avg=None, temp_daily_max=None, latitude=None, day_of_year=None,
		r_a=None,
		temp_hourly_avg=None, rh_hourly_avg=None, wind_hourly_avg=None, elevation=None, longitude=None, hour_of_day=None
	):
		# model requirements
		self.rain = rain
		self.et0 = et0
		# weather-conditions
		self.temp_daily_min = temp_daily_min
		self.temp_daily_avg = temp_daily_avg
		self.temp_daily_max = temp_daily_max
		self.r_a = r_a
		self.temp_hourly_avg = temp_hourly_avg
		self.rh_hourly_avg = rh_hourly_avg
		self.wind_hourly_avg = wind_hourly_avg
		# determinants
		self.latitude = latitude
		self.day_of_year = day_of_year
		self.elevation = elevation
		self.longitude = longitude
		self.hour_of_day = hour_of_day

	
	@staticmethod
	def get_intermediates(latitude, day_of_year):
		
		doy_in_radians = ((2*math.pi)/365) * day_of_year
		d_r = 1 + 0.033 * math.cos(doy_in_radians)
		phi = latitude * (math.pi/180)
		delta = 0.409 * math.sin(doy_in_radians - 1.39)
		omega_s = math.acos(-math.tan(phi) * math.tan(delta))
		
		return doy_in_radians, d_r, phi, delta, omega_s

	
	@staticmethod
	def get_pocra_daily_radiation(latitude, day_of_year):
		_, d_r, phi, delta, omega_s = Weather.get_intermediates(latitude, day_of_year)
		
		r_a = (24*60/math.pi) * Weather.G_sc * d_r * (
			omega_s*math.sin(phi)*math.sin(delta)
			+ math.cos(phi)*math.sin(omega_s)*math.cos(delta)
		)

		return r_a


	@staticmethod
	def get_pocra_daily_et0(
		temp_min, temp_avg, temp_max, r_a=None, latitude=None, day_of_year=None
	):
		
		r_a = r_a or Weather.get_pocra_daily_radiation(latitude, day_of_year)
		et0 = 0.0023 * (temp_avg + 17.28) * ((temp_max-temp_min)**0.5) * r_a * 0.408

		return r_a, et0

	
	@staticmethod
	def get_pocra_hourly_radiation(latitude, longitude, day_of_year, hour):

		doy_in_radians, d_r, phi, delta, omega_s = Weather.get_intermediates(latitude, day_of_year)
		b = (2*math.pi/364) * (day_of_year-81)
		S_c = (0.1645 * math.sin(2*b)) - (0.1255 * math.cos(b)) - (0.025 * math.sin(b))
		t = hour - 0.5
		omega = (math.pi/12) * ((t + 0.06667 * (277.5 - (360-longitude)) + S_c) - 12)
		
		if abs(omega) > omega_s:
			r_a = 0
		else:
			omega_2 = omega + math.pi/24 * Weather.t1
			omega_1 = omega - math.pi/24 * Weather.t1
			r_a = (
				(60*12/math.pi) * Weather.G_sc * d_r * (
					(omega_2-omega_1) * math.sin(phi) * math.sin(delta) + (
						math.cos(phi) * math.cos(delta)
						* (math.sin(omega_2)-math.sin(omega_1))
					)
				)
			)

		return r_a

	
	@staticmethod
	def get_pocra_hourly_et0(
		latitude, day_of_year, temp_daily_max, temp_daily_min, temp_hourly_avg, rh_hourly_avg, wind_hourly_avg, elevation,
		r_a=None, longitude=None, hour=None
	):

		e_0_T_hr = 0.6108 * math.exp(17.27*temp_hourly_avg/(temp_hourly_avg+237.3))
		e_a = e_0_T_hr * rh_hourly_avg/100

		r_a = r_a or Weather.get_pocra_hourly_radiation(latitude, longitude, day_of_year, hour)
		
		R_s = Weather.k_Rs * (temp_daily_max-temp_daily_min)**0.5 * r_a
		R_ns = (1-Weather.alpha) * R_s
		temp_avg_k = temp_hourly_avg + 273.15
		R_so = (0.75 + 2*(10**(-5))*elevation) * r_a
		if R_so == 0:
			R_nl = Weather.sigma * (temp_avg_k**4) * (0.34 - 0.14*(e_a)) * (1.35*0.5 - 0.35)
		else:
			R_nl = Weather.sigma * (temp_avg_k**4) * (0.34 - 0.14*(e_a)) * (1.35*R_s/R_so - 0.35)
		R_n = R_ns - R_nl

		## currently, not using <N> to determine <G_hr>;
		## instead using <r_a> as proxy
		# doy_in_radians, d_r, phi, delta, omega_s = Weather.get_intermediates(latitude, day_of_year)
		# N = 24/math.pi * omega_s
		if r_a == 0:
			G_hr = 0.5 * R_n
		else:
			G_hr = 0.1 * R_n
		# sengaon hingoli
		# kada beed
		P = 101.3*((293-0.0065*elevation)/293)**5.26
		gamma = 0.665 * 10**(-3) * P
		cap_delta = 4098 * (0.6108* math.exp((17.27*temp_hourly_avg)/(temp_hourly_avg+237.3))) / (temp_hourly_avg+237.3)**2

		et0 = (
			(0.408 * cap_delta * (R_n-G_hr) + gamma*(37/temp_avg_k)*wind_hourly_avg*(e_0_T_hr-e_a))
			/ (cap_delta + gamma*(1+0.34*wind_hourly_avg))
		)

		return r_a, et0



class Water:
	"""
	This represents the components of water-balance
	over the duration of model simulation.
	This class also provides the function <run_pocra_sm_model_for_day>
	that simulates PoCRA's soil-moisture model for a single daily time-step.
	"""

	def __init__(self,
		pri_runoff=None, infil=None, aet=None, sec_runoff=None,
		gw_rech=None, avail_sm=None, pet=None
	):

		self.pri_runoff = pri_runoff
		self.infil = infil
		self.aet = aet
		self.sec_runoff = sec_runoff
		self.gw_rech = gw_rech
		self.avail_sm = avail_sm
		self.pet = pet


	@staticmethod
	def get_pocra_pet_for_time_step(
		kc, et0=None, r_a=None, latitude=None, day_of_year=None,
		temp_daily_min=None, temp_daily_avg=None, temp_daily_max=None,
		temp_hourly_avg=None, rh_hourly_avg=None, wind_hourly_avg=None,
		elevation=None, longitude=None, hour_of_day=None,
		**ignorable_kwargs
	):

		if et0 is not None:
			pet = kc * et0
		elif hour_of_day is not None:
			r_a, et0 = Weather.get_pocra_hourly_et0(
				latitude, day_of_year, temp_daily_max, temp_daily_min, temp_hourly_avg,
				rh_hourly_avg, wind_hourly_avg, elevation, r_a, longitude, hour_of_day
			)
			pet = kc * et0
		else:
			r_a, et0 = Weather.get_pocra_daily_et0(
				temp_daily_min, temp_daily_avg, temp_daily_max, r_a, latitude, day_of_year
			)
			pet = kc * et0
		
		return r_a, et0, pet

	
	@staticmethod
	def run_pocra_sm_model_for_time_step(
		layer_1_thickness, layer_2_thickness, # layer-dimensions
		sm1_frac, sm2_frac, # soil-moisture state at day-start
		wp, fc, sat, smax, w1, w2, perc_factor, # soil-properties
		depletion_factor, # parameter determined only by crop
		rain, # parameter determined only by weather
		pet # parameter determined by weather and crop
	):
		l1 = layer_1_thickness
		l2 = layer_2_thickness
		prev_avail_sm = (sm1_frac * l1 + sm2_frac * l2 - wp * (l1+l2)) * 1000

		####### pri_runoff #######
		s_swat = smax * ( 1 - 
			prev_avail_sm / ( prev_avail_sm + math.exp(w1 - w2 * prev_avail_sm) )
		)
		ia_swat = 0.2 * s_swat
		if rain <= ia_swat:
			pri_runoff = 0
		else:
			pri_runoff = ((rain - ia_swat)**2 ) / (rain + 0.8*s_swat)
		
		####### infil #######
		infil = rain - pri_runoff
		
		####### aet #######
		if (sm1_frac < wp):
			ks = 0
		elif ( sm1_frac > (fc * (1-depletion_factor) + depletion_factor * wp) ):
			ks = 1
		else:
			ks = (sm1_frac - wp) / (fc - wp) / (1-depletion_factor)
		aet = ks * pet
		
		# sm1_before r_to_second_layer(in metres) and sm2_before gw_rech
		sm1_before = ((sm1_frac * l1) + ((infil - aet) / 1000)) / l1
		if (sm1_before < fc):
			r_to_second_layer = 0
		elif (sm2_frac < sat):
			r_to_second_layer = min(
				(sat - sm2_frac) * l2,
				(sm1_before - fc) * l1 * perc_factor
			)
		else:
			r_to_second_layer = 0
		sm2_before = (sm2_frac * l2 + r_to_second_layer) / l2
		
		####### sec_runoff #######
		candidate_new_sm1_frac = (sm1_before * l1 - r_to_second_layer) / l1
		candidate_sec_runoff = ( candidate_new_sm1_frac - sat ) * l1 * 1000
		sec_runoff = max(candidate_sec_runoff, 0)
		new_sm1_frac = min(candidate_new_sm1_frac, sat)
		
		####### gw_rech #######
		candidate_gw_rech = (sm2_before - fc) * l2 * perc_factor * 1000
		gw_rech = max(candidate_gw_rech, 0)
		candidate_sm2_frac = (sm2_before * l2 - gw_rech / 1000) / l2
		new_sm2_frac = min(candidate_sm2_frac, sat)

		####### avail_sm #######
		avail_sm = (new_sm1_frac * l1 + new_sm2_frac * l2 - wp * (l1+l2)) * 1000


		return (
			Water(pri_runoff, infil, aet, sec_runoff, gw_rech, avail_sm, pet),
			{'sm1_frac': new_sm1_frac, 'sm2_frac': new_sm2_frac},
		)
	# @staticmethod
	# def run_pocra_sm_model_for_time_step(
	# 	layer_1_thickness, layer_2_thickness, # layer-dimensions
	# 	prev_avail_sm, sm1_frac, sm2_frac, # soil-moisture state at day-start
	# 	wp, fc, sat, smax, w1, w2, perc_factor, # soil-properties
	# 	depletion_factor, # parameter determined only by crop
	# 	rain, # parameter determined only by weather
	# 	pet # parameter determined by weather and crop
	# ):
	# 	l1 = layer_1_thickness
	# 	l2 = layer_2_thickness

	# 	####### pri_runoff #######
	# 	s_swat = smax * ( 1 - 
	# 		prev_avail_sm / ( prev_avail_sm + math.exp(w1 - w2 * prev_avail_sm) )
	# 	)
	# 	ia_swat = 0.2 * s_swat
	# 	if rain <= ia_swat:
	# 		pri_runoff = 0
	# 	else:
	# 		pri_runoff = ((rain - ia_swat)**2 ) / (rain + 0.8*s_swat)
		
	# 	####### infil #######
	# 	infil = rain - pri_runoff
		
	# 	####### aet #######
	# 	if (sm1_frac < wp):
	# 		ks = 0
	# 	elif ( sm1_frac > (fc * (1-depletion_factor) + depletion_factor * wp) ):
	# 		ks = 1
	# 	else:
	# 		ks = (sm1_frac - wp) / (fc - wp) / (1-depletion_factor)
	# 	aet = ks * pet
		
	# 	# sm1_before r_to_second_layer(in metres) and sm2_before gw_rech
	# 	sm1_before = ((sm1_frac * l1) + ((infil - aet) / 1000)) / l1
	# 	if (sm1_before < fc):
	# 		r_to_second_layer = 0
	# 	elif (sm2_frac < sat):
	# 		r_to_second_layer = min(
	# 			(sat - sm2_frac) * l2,
	# 			(sm1_before - fc) * l1 * perc_factor
	# 		)
	# 	else:
	# 		r_to_second_layer = 0
	# 	sm2_before = (sm2_frac * l2 + r_to_second_layer) / l2
		
	# 	####### sec_runoff #######
	# 	candidate_new_sm1_frac = (sm1_before * l1 - r_to_second_layer) / l1
	# 	candidate_sec_runoff = ( candidate_new_sm1_frac - sat ) * l1 * 1000
	# 	sec_runoff = max(candidate_sec_runoff, 0)
	# 	new_sm1_frac = min(candidate_new_sm1_frac, sat)
		
	# 	####### gw_rech #######
	# 	candidate_gw_rech = (sm2_before - fc) * l2 * perc_factor * 1000
	# 	gw_rech = max(candidate_gw_rech, 0)
	# 	candidate_sm2_frac = (sm2_before * l2 - gw_rech / 1000) / l2
	# 	new_sm2_frac = min(candidate_sm2_frac, sat)

	# 	####### avail_sm #######
	# 	avail_sm = (new_sm1_frac * l1 + new_sm2_frac * l2 - wp * (l1+l2)) * 1000


	# 	return (
	# 		Water(pri_runoff, infil, aet, sec_runoff, gw_rech, avail_sm, pet),
	# 		{'avail_sm': avail_sm, 'sm1_frac': new_sm1_frac, 'sm2_frac': new_sm2_frac},
	# 	)