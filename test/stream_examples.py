import os
import csv
from datetime import datetime, date, timedelta

from pocragis_models.models import Drainage


os.chdir(os.path.dirname(__file__))
with open('example_drainage_input.csv', 'r', newline='') as f:
	drainage_data = list(csv.DictReader(f))

connected_streams = {}
for row in drainage_data:
	connected_streams[row['stream_id']] = Drainage.ConnectedStream(
		Drainage.Stream.Channel(*[float(row[v]) for v in [
			'watershed_area', 'length', 'width_bottom', 'channel_slope', 'fraction_deep_aquifer', 'zch',
			'hydraulic_conductivity', 'evaporation_coefficient', 'mannigs', 'bank_flow_recession', 'potential_evaporation'
		]]),
		[Drainage.Stream.Transient(volume_out=0, volume_stored_end_timestep=0)]
	)

i = 1
while str(i) in drainage_data[0].keys():
	i += 1
total_time_steps = i - 1

for row in drainage_data:
	connected_streams[row['stream_id']].sources.extend([
		connected_streams[v.strip()] for v in row['sources'].split(',') if v.strip() != ''
	])
	connected_streams[row['stream_id']].runoffs = [float(row[str(i+1)]) for i in range(total_time_steps)]
	connected_streams[row['stream_id']].id = row['stream_id']

drainage = Drainage(list(connected_streams.values()))


for i in range(total_time_steps):
	
	for cs in drainage.connected_streams:
		cs.next_runoff_per_area_in_watershed = cs.runoffs[i]

	drainage.compute_drainage_model_transients_for_latest_time_step()


with open('example_drainage_output.csv', 'w', newline='') as f:
	fieldnames = [
		'runoff_per_area_in_watershed', 'swat_runoff', 'total_volume_stored', 'volume_in', 'discharge',
		'transmission_loss', 'bankin', 'return_flow_from_bank', 'evaporation_loss', 'total_loss',
		'volume_after_loss', 'volume_out', 'volume_stored_end_timestep', 'cross_section',
		'depth_water_level', 'width_water_level', 'wetted_perimeter', 'hydraulic_radius',
		'velocity', 'travel_time', 'fraction_time_step', 'storage_coeffecient'
	]
	writer = csv.writer(f)
	writer.writerow(['stream_id', 'time_step'] + fieldnames)
	for cs in drainage.connected_streams:
		for i in range(total_time_steps):
			writer.writerow([cs.id, str(i)] + [getattr(cs.transients[i], fn) for fn in fieldnames])