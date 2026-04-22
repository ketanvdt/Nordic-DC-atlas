CREATE TABLE IF NOT EXISTS power_zone_profiles (
  zone_code TEXT PRIMARY KEY,
  country CHAR(2) NOT NULL,
  price_3y_eur_mwh DOUBLE PRECISION NOT NULL,
  capacity_score DOUBLE PRECISION NOT NULL,
  source_note TEXT NOT NULL
);

INSERT INTO power_zone_profiles (zone_code, country, price_3y_eur_mwh, capacity_score, source_note) VALUES
  ('SE1', 'SE', 38, 0.85, 'Svk directional v1'),
  ('SE2', 'SE', 40, 0.80, 'Svk directional v1'),
  ('SE3', 'SE', 66, 0.35, 'Svk directional v1'),
  ('SE4', 'SE', 78, 0.25, 'Svk directional v1'),
  ('NO1', 'NO', 72, 0.30, 'Statnett directional v1'),
  ('NO2', 'NO', 70, 0.32, 'Statnett directional v1'),
  ('NO3', 'NO', 45, 0.78, 'Statnett directional v1'),
  ('NO4', 'NO', 41, 0.82, 'Statnett directional v1'),
  ('NO5', 'NO', 60, 0.55, 'Statnett directional v1'),
  ('FI',  'FI', 58, 0.62, 'Fingrid directional v1')
ON CONFLICT (zone_code) DO UPDATE SET
  price_3y_eur_mwh = EXCLUDED.price_3y_eur_mwh,
  capacity_score = EXCLUDED.capacity_score,
  source_note = EXCLUDED.source_note;
