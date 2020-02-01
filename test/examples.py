import csv
from datetime import datetime, timedelta

import pocragis_models.simulate as pgm_simulate


with open('example_input_data.csv', 'r', newline='') as f:
	data = list(csv.DictReader(f))


for d in data:
	
	for p in ['daily_rain', 'daily_temp_min', 'daily_temp_avg', 'daily_temp_max']:
		d[p] = [float(v.strip(" '")) for v in d[p].strip('[]').split(',')]
	for p in ['rain', 'temp_avg', 'rh_avg', 'wind_avg']:
		daily_data = d[p].strip('[]').split(']')
		d[p] = []
		for dd in daily_data:
			d[p].extend([float(v.strip(" '")) for v in dd.strip(' ,[]').split(',')])

	# daily_psmm_sim = pgm_simulate.PocraSMModelSimulation(
	# 	soil_texture='clayey', soil_depth_category='deep to very deep (> 50 cm)', lulc_type='kharif', slope=3,
	# 	step_unit='DAY',
	# 	weathers={'rain': d['daily_rain']},
	# 	crop='soyabean',
	# 	pet=[0.5]*365
	# )

	# daily_psmm_sim.run()

	# daily_psmm_sim = pgm_simulate.PocraSMModelSimulation(
	# 	soil_texture='clayey', soil_depth_category='deep to very deep (> 50 cm)', lulc_type='kharif', slope=3,
	# 	step_unit='DAY',
	# 	weathers={'rain': [1]*365, 'et0': [1]*365},
	# 	crop='bajri'
	# )

	# daily_psmm_sim.run()

	# daily_psmm_sim = pgm_simulate.PocraSMModelSimulation(
	# 	soil_texture='clayey', soil_depth_category='deep to very deep (> 50 cm)', lulc_type='kharif', slope=3,
	# 	step_unit='DAY',
	# 	weathers={
	# 		'rain': d['daily_rain'], 'temp_daily_min': d['daily_temp_min'],
	# 		'temp_daily_avg': d['daily_temp_avg'], 'temp_daily_max': d['daily_temp_max'],
	# 		'r_a': [1000]*365},
	# 	crop='bajri'
	# )

	# daily_psmm_sim.run()

	daily_psmm_sim = pgm_simulate.PocraSMModelSimulation(
		soil_texture='clayey', soil_depth_category='deep to very deep (> 50 cm)', lulc_type='kharif', slope=3,
		step_unit='DAY',
		weathers={
			'rain': d['daily_rain'], 'temp_daily_min': d['daily_temp_min'],
			'temp_daily_avg': d['daily_temp_avg'], 'temp_daily_max': d['daily_temp_max'],
		},
		latitude=float(d['lat']),
		crop='bajri'
	)

	daily_psmm_sim.run()

	# print(daily_psmm_sim.aet)


	# hourly_psmm_sim = pgm_simulate.PocraSMModelSimulation(
	# 	soil_texture='clayey', soil_depth_category='deep to very deep (> 50 cm)', lulc_type='kharif', slope=3,
	# 	step_unit='HOUR',
	# 	weathers={'rain': [1]*365*24},
	# 	crop='bajri',
	# 	pet=[0.5]*365*24
	# )

	# hourly_psmm_sim.run()

	# hourly_psmm_sim = pgm_simulate.PocraSMModelSimulation(
	# 	soil_texture='clayey', soil_depth_category='deep to very deep (> 50 cm)', lulc_type='kharif', slope=3,
	# 	step_unit='HOUR',
	# 	weathers={'rain': [1]*365*24, 'et0': [1]*365*24},
	# 	crop='bajri'
	# )

	# hourly_psmm_sim.run()

	# hourly_psmm_sim = pgm_simulate.PocraSMModelSimulation(
	# 	soil_texture='clayey', soil_depth_category='deep to very deep (> 50 cm)', lulc_type='kharif', slope=3,
	# 	step_unit='HOUR',
	# 	weathers={
	# 		'rain':[1]*365*24, 'temp_daily_min': [25]*365*24, 'temp_hourly_avg': [30]*365*24, 'temp_daily_max': [35]*365*24,
	# 		'rh_hourly_avg': [50]*365*24, 'wind_hourly_avg': [20]*365*24,
	# 		'r_a': [1000]*365*24
	# 	},
	# 	elevation=350,
	# 	crop='bajri'
	# )

	# hourly_psmm_sim.run()

	hourly_psmm_sim = pgm_simulate.PocraSMModelSimulation(
		soil_texture='clayey', soil_depth_category='deep to very deep (> 50 cm)', lulc_type='kharif', slope=3,
		step_unit='HOUR',
		weathers={
			'rain': d['rain'], 'temp_daily_min': [v for v in d['daily_temp_min'] for i in range(24)],
			'temp_hourly_avg': d['temp_avg'], 'temp_daily_max': [v for v in d['daily_temp_max'] for i in range(24)],
			'rh_hourly_avg': d['rh_avg'], 'wind_hourly_avg': d['wind_avg'],
		},
		latitude=20, longitude=78, elevation=350,
		crop='bajri'
	)

	hourly_psmm_sim.run()

	with open(f'{d["rain_circle"].replace(" ", "_")}_example_output.csv', 'w', newline='') as f:
		print(f'Writing output for {d["rain_circle"]}...')
		fieldnames = ['date-time', 'rain', 'temp_daily_min', 'temp_hourly_avg', 'temp_daily_max', 'rh_hourly_avg', 'wind_hourly_avg', 'r_a', 'et0']
		writer = csv.writer(f)
		writer.writerow(fieldnames)
		s = hourly_psmm_sim
		writer.writerows([[
			datetime(2018, 6, 1) + timedelta(
				days=s.day_of_year[i] + (-152 if s.day_of_year[i]>=152 else 213),
				hours=s.hour_of_day[i]-1
			), *[round(v, 2) for v in [
				s.rain[i], s.temp_daily_min[i], s.temp_hourly_avg[i], s.temp_daily_max[i],
				s.rh_hourly_avg[i], s.wind_hourly_avg[i], s.r_a[i], s.et0[i]
			]]
		] for i in range(365*24)])