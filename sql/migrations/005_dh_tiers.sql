CREATE TABLE IF NOT EXISTS dh_city_tiers (
  city_key TEXT PRIMARY KEY,
  city_name TEXT NOT NULL,
  country CHAR(2) NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  readiness_tier SMALLINT NOT NULL,
  operator_name TEXT NOT NULL,
  note TEXT
);

INSERT INTO dh_city_tiers (city_key, city_name, country, lat, lon, readiness_tier, operator_name, note) VALUES
  ('stockholm', 'Stockholm', 'SE', 59.3293, 18.0686, 2, 'Stockholm Exergi', 'Large network and existing DC heat partnerships'),
  ('gothenburg', 'Gothenburg', 'SE', 57.7089, 11.9746, 2, 'Goteborg Energi', 'Dense district heating system'),
  ('malmo', 'Malmo', 'SE', 55.6049, 13.0038, 1, 'E.ON', 'Urban network with mixed industrial fit'),
  ('uppsala', 'Uppsala', 'SE', 59.8586, 17.6389, 1, 'Vattenfall', 'Solid city-scale system'),
  ('vasteras', 'Vasteras', 'SE', 59.6099, 16.5448, 1, 'Malarenergi', 'Industrial heat integration potential'),
  ('orebro', 'Orebro', 'SE', 59.2753, 15.2134, 1, 'E.ON', 'Regional network'),
  ('linkoping', 'Linkoping', 'SE', 58.4108, 15.6214, 1, 'Tekniska verken', 'Municipal utility openness'),
  ('lulea', 'Lulea', 'SE', 65.5848, 22.1547, 2, 'Lulea Energi', 'High relevance for northern siting'),
  ('umea', 'Umea', 'SE', 63.8258, 20.2630, 1, 'Umea Energi', 'Growing network'),
  ('oslo', 'Oslo', 'NO', 59.9139, 10.7522, 2, 'Fortum Oslo Varme', 'Major DH integration opportunities'),
  ('bergen', 'Bergen', 'NO', 60.3913, 5.3221, 1, 'BKK/municipal', 'Moderate readiness'),
  ('trondheim', 'Trondheim', 'NO', 63.4305, 10.3951, 1, 'Statkraft Varme', 'Campus/urban demand nodes'),
  ('stavanger', 'Stavanger', 'NO', 58.9700, 5.7331, 0, 'Local mixed', 'Lower DH network maturity'),
  ('tromso', 'Tromso', 'NO', 69.6492, 18.9553, 1, 'Arva/municipal', 'Cold climate but limited scale'),
  ('helsinki', 'Helsinki', 'FI', 60.1699, 24.9384, 2, 'Helen', 'Mature DH ecosystem'),
  ('espoo', 'Espoo', 'FI', 60.2055, 24.6559, 2, 'Fortum', 'Strong integration potential'),
  ('vantaa', 'Vantaa', 'FI', 60.2934, 25.0378, 2, 'Vantaan Energia', 'High readiness'),
  ('tampere', 'Tampere', 'FI', 61.4978, 23.7610, 1, 'Tampereen Energia', 'Good network footprint'),
  ('turku', 'Turku', 'FI', 60.4518, 22.2666, 1, 'Turku Energia', 'Moderate readiness'),
  ('oulu', 'Oulu', 'FI', 65.0121, 25.4651, 1, 'Oulun Energia', 'Northern market relevance')
ON CONFLICT (city_key) DO UPDATE SET
  city_name = EXCLUDED.city_name,
  country = EXCLUDED.country,
  lat = EXCLUDED.lat,
  lon = EXCLUDED.lon,
  readiness_tier = EXCLUDED.readiness_tier,
  operator_name = EXCLUDED.operator_name,
  note = EXCLUDED.note;
