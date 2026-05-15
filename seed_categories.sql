-- Seed service categories into the database
-- This maps frontend category IDs to database category names

INSERT INTO categories (name) VALUES
  ('Healthcare'),
  ('Cleaning'),
  ('Tutoring'),
  ('Logistics'),
  ('Web Development'),
  ('Graphic Design'),
  ('Writing & Content'),
  ('Photography'),
  ('Plumbing & Handyman'),
  ('Consulting'),
  ('Marketing'),
  ('Video Production'),
  ('Pet Care'),
  ('Fitness & Training'),
  ('Event Planning')
ON CONFLICT (name) DO NOTHING;

-- Verify categories were created
SELECT id, name FROM categories ORDER BY id;
