CREATE TABLE IF NOT EXISTS municipality_lookup (
  municipality_code TEXT PRIMARY KEY,
  municipality_name TEXT NOT NULL,
  country CHAR(2) NOT NULL
);

INSERT INTO municipality_lookup (municipality_code, municipality_name, country) VALUES
  ('SE-0180', 'Stockholm', 'SE'),
  ('SE-1280', 'Malmo', 'SE'),
  ('SE-1480', 'Gothenburg', 'SE'),
  ('SE-2580', 'Lulea', 'SE'),
  ('NO-0301', 'Oslo', 'NO'),
  ('NO-1103', 'Stavanger', 'NO'),
  ('NO-4601', 'Bergen', 'NO'),
  ('NO-5001', 'Trondheim', 'NO'),
  ('FI-091', 'Helsinki', 'FI'),
  ('FI-049', 'Espoo', 'FI'),
  ('FI-092', 'Vantaa', 'FI'),
  ('FI-837', 'Tampere', 'FI')
ON CONFLICT (municipality_code) DO UPDATE SET
  municipality_name = EXCLUDED.municipality_name,
  country = EXCLUDED.country;
