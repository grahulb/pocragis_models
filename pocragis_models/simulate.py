import os
import csv

from .models import *


class PocraSMModelSimulation:
	"""
	This represents the PoCRA's SM Model for a particular location
	and its simulation over days(time-steps).
	
	Usage:
	>>> from pocra_sm_model import *
	>>> psmm = PocraSMModelSimulation(<various input-parameters>)
	>>> psmm.run()
	>>> aet_values_list = psmm.aet

	In general, after <run>ning the simulation, the list (indexed by time-step)
	of any of the following water-components can be obtained
	(like aet's list was obtained above): avail_sm, pri_runoff, infil,
	aet, pet, sec_runoff and gw_rech.
	"""

	def __init__(self,
		# field-related attributes
		soil_texture=None, soil_depth_category=None, lulc_type=None, slope=None, field=None,
		# simulation time-stepping; current options for step_unit are 'DAY' and 'HOUR'
		step_unit='DAY',
		# weather-related attributes
		weathers=None,
		# rain=None, et0=None,
		# r_a=None, temp_daily_min=None, temp_daily_avg=None, temp_daily_max=None,
		latitude=None,
		# temp_hourly_avg=None, rh_hourly_avg=None, wind_hourly_avg=None,
		elevation=None, longitude=None,
		# crop
		crop=None,
		# attribute determined by crop+weather
		pet=None,
		# attributes setting the starting state for the simulation
		model_state_at_start=None, sowing_date_offset=None, sowing_threshold=None
	):
		"""
		TODO: update this __doc__ as per the new code
		Set model entities.
		field, crop, weathers and waters are instances(plurals are <lists> of instances)
		of corresponding classes.
		state should be a <dict> with three model properties:
		1. key 'avail_sm' : available soil-moisture at the beginning of simulation
		2. key 'sm1_frac' : soil-moisture content in layer 1 expressed as a fraction
		3. key 'sm2_frac' : soil-moisture content in layer 2 expressed as a fraction
		"""

		self.field = field or Field(
			soil_texture, soil_depth_category, lulc_type, slope, 24 if step_unit=='HOUR' else 1
		)
		
		self.step_unit = step_unit

		self.model_state = model_state_at_start or {
			'sm1_frac': self.field.wp, 'sm2_frac': self.field.wp,
			'day_of_year': 152, 'hour_of_day': 1 # 12 am to 1am on June 1st
		}
		if all(isinstance(weather, Weather) for weather in weathers):
			self.weathers = weathers
		else:
			if all((type(weather) == dict and 'rain' in weather) for weather in weathers):
				self.weathers = [Weather(**weather) for weather in weathers]
			elif type(weathers) == dict and 'rain' in weathers and all(type(v) == list for v in weathers.values()):
				self.weathers = [Weather(**{param: weathers[param][i] for param in weathers}) for i in range(len(weathers['rain']))]
			try:
				for i in range(len(self.weathers)):
					w = self.weathers[i]
					if step_unit == 'DAY':
						w.day_of_year = self.model_state['day_of_year'] + i
					elif step_unit == 'HOUR':
						hour_of_year_at_start = (self.model_state['day_of_year']-1) * 24 + (self.model_state['hour_of_day']-1)
						w.day_of_year = (((hour_of_year_at_start+i) // 24) + 1) % 365
						w.hour_of_day = ((hour_of_year_at_start+i) % 24) + 1
					w.latitude = latitude
					w.longitude = longitude
					w.elevation = elevation
			except Exception as e:
				raise e#Exception('Problem with weather-data input')

			# self.weathers = [Weather(rain=r) for r in rain]
			# if pet is not None:
			# 	self.pet = pet
			# elif et0 is not None:
			# 	for i in range(len(self.weathers)):
			# 		self.weathers[i].et0 = et0[i]
			# else:
			
			# for wthr_param in [
			# 	'rain', 'pet', 'et0', 'r_a',
			# 	'temp_daily_min', 'temp_daily_avg', 'temp_daily_max', 'day_of_year',
			# 	'temp_hourly_avg', 'rh_hourly_avg', 'wind_hourly_avg', 'hour_of_day'
			# ]:
			# 	if locals()[wthr_param] is not None:
			# 		for i in range(len(locals()[wthr_param])):
			# 			setattr(self.weathers[i], wthr_param, locals()[wthr_param][i])

				# print(locals()['lulc_type'])
				# return
				# for i in range(len(self.weathers)):
				# 	self.weathers[i].temp_daily_min = temp_daily_min[i]
				# 	self.weathers[i].temp_daily_avg = temp_daily_avg[i]
				# 	self.weathers[i].temp_daily_max = temp_daily_max[i]
				# if r_a is not None:
				# 	for i in range(len(self.weathers)):
				# 		self.weathers[i].r_a = r_a[i]
				# else:
				# 	for i in range(len(self.weathers)):
				# 		self.weathers[i].latitude = latitude

		self.pet = pet

		self.simulation_length = len(self.weathers)

		self.crop = Crop(crop) if isinstance(crop, str) else crop

		self.sowing_date_offset = sowing_date_offset
		self.sowing_threshold = sowing_threshold or lookups.DEFAULT_SOWING_THRESHOLD
			

		self.waters = [None]*self.simulation_length

		self._direct_param_access = {}


	def __getattr__(self, name):

		if name in self._direct_param_access:
			return self._direct_param_access[name]
		else:
			if name in [
				'pri_runoff', 'infil', 'aet', 'sec_runoff', 'gw_rech', 'avail_sm', 'pet'
			]:
				value = [getattr(w, name) for w in self.waters]
			elif name in [
				'rain', 'et0', 'temp_daily_min', 'temp_daily_avg', 'temp_daily_max',
				'r_a', 'temp_hourly_avg', 'rh_hourly_avg', 'wind_hourly_avg',
				'latitude',	'elevation', 'longitude', 'day_of_year', 'hour_of_day'
			]:
				value = [getattr(w, name) for w in self.weathers]
			self._direct_param_access[name] = value
			return value
	

	def computation_before_iteration(self):
		
		# determine layer_1_thickness, layer_2_thickness
		if (self.field.soil_depth <= self.crop.root_depth): # thin soil layer
			self.layer_1_thickness = self.field.soil_depth - 0.05
			self.layer_2_thickness = 0.05
		else:
			self.layer_1_thickness = self.crop.root_depth
			self.layer_2_thickness = self.field.soil_depth - self.crop.root_depth

		if self.sowing_date_offset is None:
			if self.pet is not None:
				i = 0
				while(self.pet[i] == 0):
					i += 1
				self.sowing_date_offset = i
			else:
				if self.crop.is_pseudo_crop:
					self.sowing_date_offset = 0
				else:
					# determine sowing_date_offset based on sowing_threshold logic
					accumulated_rain = 0
					for i in range(365):
						accumulated_rain += (self.weathers[i].rain if self.step_unit == 'DAY' else sum(self.weathers[24*i+j].rain for j in range(24)))
						# print(self.step_unit, self.weathers[i].rain, accumulated_rain)
						if accumulated_rain >= self.sowing_threshold:
							self.sowing_date_offset = i
							break


	def iterate(s):
		f = s.field
		for i in range(len(s.weathers)):
			if s.pet is None:
				day_of_rain_year_idx = (s.weathers[i].day_of_year-152) if (s.weathers[i].day_of_year >= 152) else (213+s.weathers[i].day_of_year)
				if s.sowing_date_offset <= day_of_rain_year_idx < (s.sowing_date_offset + len(s.crop.kc)):
					kc = s.crop.kc[day_of_rain_year_idx - s.sowing_date_offset]
				else:
					kc = 0
				# TODO : check that there is a way to compute pet from available inputs
				try:
					# params_for_pet_for_time_step = {
					# 	p: getattr(weather, p, None) for p in [
					# 		'et0', 'temp_daily_min', 'temp_daily_avg', 'temp_daily_max', 'r_a', 'latitude', 'day_of_year',
					# 		'temp_hourly_avg', 'rh_hourly_avg', 'wind_hourly_avg', 'elevation', 'longitude', 'hour_of_day'
					# 	]
					# }
					# params_for_pet_for_day['day_of_year'] = ((i+1)+151) if (i+1) <= 214 else (215-i) # leap-years may be tackled if year can be provided by user
					R_a_for_time_step, et0_for_time_step, pet_for_time_step = Water.get_pocra_pet_for_time_step(kc, **s.weathers[i].__dict__)#**params_for_pet_for_day)
					s.weathers[i].r_a = R_a_for_time_step
					s.weathers[i].et0 = et0_for_time_step
				except Exception as e:
					print(i, s.weathers[i].__dict__)
					raise e
			else:
				pet_for_time_step = s.pet[i]

			s.waters[i], s.model_state = Water.run_pocra_sm_model_for_time_step(
				s.layer_1_thickness, s.layer_2_thickness,
				s.model_state['sm1_frac'], s.model_state['sm2_frac'],
				f.wp, f.fc, f.sat, f.smax, f.w1, f.w2, f.perc_factor,
				s.crop.depletion_factor,
				s.weathers[i].rain, pet_for_time_step
			)

		s.pet = [w.pet for w in s.waters]
	
	
	def computation_after_iteration(self):
		
		self.crop_end_index = min(self.sowing_date_offset + len(self.crop.kc), 364)



	def run(self):
		self.computation_before_iteration()
		self.iterate()
		self.computation_after_iteration()



class SimulationIO:
	"""
	This class provides input-output facilities
	to build a <PocraSMModelSimulation> instance.
	"""
	
	@staticmethod
	def create_weathers_from_csv_file(filepath):

		if os.path.exists(filepath):
			with open(filepath, newline='') as f:
				return [
					Weather(**{k: float(v) for k, v in row.items()}) for row in csv.DictReader(f)
				]
	

	@staticmethod
	def output_water_components_to_csv(psmm, components=[], filepath='results.csv'):

		if (isinstance(psmm, PocraSMModelSimulation)
			and len(psmm.waters) > 0 and all(isinstance(w, Water) for w in psmm.waters)
		):
			rows = [{
				c: (getattr(psmm.waters[i], c) if hasattr(psmm.waters[i], c)
					else getattr(psmm.weathers[i], c) if hasattr(psmm.weathers[i], c)
					else 'No such component found')
				for c in components
			} for i in range(len(psmm.weathers))]
			
			with open(filepath, 'w', newline='') as f:
				writer = csv.DictWriter(f, fieldnames=components)
				writer.writeheader()
				writer.writerows(rows)