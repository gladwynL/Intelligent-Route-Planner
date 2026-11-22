-- =====================================================================
-- Intelligent Route Planning System — demonstration data
--
-- Based on Phase II, Part B.  All relationships, locations, routes,
-- observations and ratings are unchanged from the Phase II sample data.
-- Changes for Phase III (documented in docs/TEST_RESULTS.md):
--   * Account names/emails are fictional demo identities (example.com)
--     instead of real student details, so the repository can be shared.
--   * password_hash values are real Werkzeug scrypt hashes of the
--     documented DEMO passwords (see docs/DEMO_CREDENTIALS.md) instead of
--     the Phase II placeholders, so the demo accounts can actually log in.
--   * Identity sequences are advanced after the explicit-ID inserts, so
--     rows created later by the application do not collide (Phase II defect).
-- =====================================================================

BEGIN;

INSERT INTO app_user (user_id, full_name, email, password_hash, user_role, created_at) VALUES
 (1, 'Avery Morgan',  'avery.morgan@example.com',  'scrypt:32768:8:1$XGwh9ENeUpsGldnJ$b5862178a8180bba7394450b458369a071473ced44e51d282f68e993fdc6babb0edb590874f2dbf94d486cf12d6f423ef6278f9d0df2af7349ae0968e3761398', 'admin', '2026-10-20 09:00'),
 (2, 'Jordan Rivera', 'jordan.rivera@example.com', 'scrypt:32768:8:1$2NvjkgYBgl83Imyw$4518b8f5c408956d28b6f42000e0ac6e285720139a9ee1598ce4d20cffb1f1cf301fa33ce6f23b98b3ef634dc0e4a6ffd5f810b48175aa844d88bf4c1158f299', 'user',  '2026-10-20 09:05'),
 (3, 'Taylor Brooks', 'taylor.brooks@example.com', 'scrypt:32768:8:1$2NvjkgYBgl83Imyw$4518b8f5c408956d28b6f42000e0ac6e285720139a9ee1598ce4d20cffb1f1cf301fa33ce6f23b98b3ef634dc0e4a6ffd5f810b48175aa844d88bf4c1158f299', 'user',  '2026-10-20 09:10'),
 (4, 'Casey Nguyen',  'casey.nguyen@example.com',  'scrypt:32768:8:1$2NvjkgYBgl83Imyw$4518b8f5c408956d28b6f42000e0ac6e285720139a9ee1598ce4d20cffb1f1cf301fa33ce6f23b98b3ef634dc0e4a6ffd5f810b48175aa844d88bf4c1158f299', 'user',  '2026-10-20 09:15'),
 (5, 'Aisha Khan',    'aisha.khan@example.com',    'scrypt:32768:8:1$2NvjkgYBgl83Imyw$4518b8f5c408956d28b6f42000e0ac6e285720139a9ee1598ce4d20cffb1f1cf301fa33ce6f23b98b3ef634dc0e4a6ffd5f810b48175aa844d88bf4c1158f299', 'user',  '2026-10-21 10:00'),
 (6, 'Daniel Chen',   'daniel.chen@example.com',   'scrypt:32768:8:1$AtCR8EGpBYXoKNBy$d08ff0d9db95a003fd3d7010cba792614ecd2f9708bfbe21759244bd6180343d37405d1058b0087816218f6a307c61a7967b391c668d2638a78c9e786e9435f8', 'guest', '2026-10-22 11:00');

INSERT INTO location (location_id, location_name, street_address, city, latitude, longitude, location_type) VALUES
 (1, 'Ontario Tech North Campus',    '2000 Simcoe Street North', 'Oshawa', 43.945520, -78.896640, 'school'),
 (2, 'Oshawa Centre',                '419 King Street West',     'Oshawa', 43.891330, -78.879520, 'public'),
 (3, 'Oshawa GO Station',            '915 Bloor Street West',    'Oshawa', 43.870610, -78.884850, 'public'),
 (4, 'Lakeridge Health Oshawa',      '1 Hospital Court',         'Oshawa', 43.904820, -78.869060, 'public'),
 (5, 'Tribute Communities Centre',   '99 Athol Street East',     'Oshawa', 43.897040, -78.859900, 'public'),
 (6, 'Whitby GO Station',            '1350 Brock Street South',  'Whitby', 43.864850, -78.938180, 'public'),
 (7, 'Lakeview Park',                '55 Lakeview Park Avenue',  'Oshawa', 43.852910, -78.838080, 'public'),
 (8, 'Durham College Whitby Campus', '1610 Champlain Avenue',    'Whitby', 43.869640, -78.899630, 'school');

INSERT INTO user_preference
 (preference_id, user_id, preferred_mode, max_walking_km, avoid_tolls, avoid_highways, prioritize_safety) VALUES
 (1, 1, 'driving', 1.0, TRUE,  FALSE, TRUE),
 (2, 2, 'transit', 2.0, TRUE,  TRUE,  TRUE),
 (3, 3, 'cycling', 3.0, TRUE,  TRUE,  TRUE),
 (4, 4, 'driving', 1.5, FALSE, FALSE, FALSE),
 (5, 5, 'walking', 5.0, TRUE,  TRUE,  TRUE),
 (6, 6, 'transit', 2.5, TRUE,  FALSE, TRUE);

INSERT INTO trip
 (trip_id, user_id, origin_location_id, destination_location_id, requested_at, departure_time, trip_status, actual_duration_min) VALUES
 (1, 1, 1, 3, '2026-11-01 07:30', '2026-11-01 08:00', 'completed', 24),
 (2, 2, 2, 1, '2026-11-01 08:10', '2026-11-01 08:30', 'completed', 29),
 (3, 3, 1, 4, '2026-11-02 12:00', '2026-11-02 12:20', 'completed', 22),
 (4, 4, 6, 5, '2026-11-03 16:00', '2026-11-03 16:30', 'completed', 35),
 (5, 5, 4, 7, '2026-11-04 09:00', '2026-11-04 09:15', 'planned',   NULL),
 (6, 6, 8, 3, '2026-11-05 17:00', '2026-11-05 17:30', 'planned',   NULL);

INSERT INTO route_option
 (route_id, trip_id, option_number, travel_mode, distance_km, estimated_duration_min, toll_cost, is_selected, generated_at) VALUES
 (1,  1, 1, 'driving', 11.80, 22, 0.00, TRUE,  '2026-11-01 07:31'),
 (2,  1, 2, 'transit', 12.60, 35, 0.00, FALSE, '2026-11-01 07:31'),
 (3,  2, 1, 'driving', 10.20, 20, 0.00, FALSE, '2026-11-01 08:11'),
 (4,  2, 2, 'transit', 10.80, 28, 0.00, TRUE,  '2026-11-01 08:11'),
 (5,  3, 1, 'cycling',  7.40, 24, 0.00, TRUE,  '2026-11-02 12:01'),
 (6,  3, 2, 'driving',  8.10, 16, 0.00, FALSE, '2026-11-02 12:01'),
 (7,  4, 1, 'driving', 15.30, 31, 2.50, TRUE,  '2026-11-03 16:01'),
 (8,  4, 2, 'transit', 16.10, 42, 0.00, FALSE, '2026-11-03 16:01'),
 (9,  5, 1, 'walking',  6.20, 76, 0.00, TRUE,  '2026-11-04 09:01'),
 (10, 5, 2, 'cycling',  6.80, 29, 0.00, FALSE, '2026-11-04 09:01'),
 (11, 6, 1, 'transit',  5.60, 19, 0.00, TRUE,  '2026-11-05 17:01'),
 (12, 6, 2, 'driving',  5.20, 13, 0.00, FALSE, '2026-11-05 17:01');

INSERT INTO route_segment
 (segment_id, route_id, sequence_no, start_location_id, end_location_id, road_name, distance_km, estimated_duration_min) VALUES
 (1,  1,  1, 1, 3, 'Simcoe Street and Bloor Street',    11.80, 22),
 (2,  2,  1, 1, 3, 'Durham Region Transit 901',         12.60, 35),
 (3,  3,  1, 2, 1, 'King Street and Simcoe Street',     10.20, 20),
 (4,  4,  1, 2, 1, 'Durham Region Transit 901',         10.80, 28),
 (5,  5,  1, 1, 4, 'Simcoe Street Cycle Route',          7.40, 24),
 (6,  6,  1, 1, 4, 'Simcoe Street North',                8.10, 16),
 (7,  7,  1, 6, 5, 'Highway 401 and Centre Street',     15.30, 31),
 (8,  8,  1, 6, 5, 'GO Transit and DRT Connection',     16.10, 42),
 (9,  9,  1, 4, 7, 'Lakeview Park Walking Trail',        6.20, 76),
 (10, 10, 1, 4, 7, 'Oshawa Creek Cycle Path',            6.80, 29),
 (11, 11, 1, 8, 3, 'Durham Region Transit 917',          5.60, 19),
 (12, 12, 1, 8, 3, 'Champlain Avenue and Bloor Street',  5.20, 13);

INSERT INTO condition_observation
 (observation_id, segment_id, observed_at, condition_type, severity, description, source_name) VALUES
 (1,  1,  '2026-11-01 07:31', 'traffic',      2, 'Moderate southbound traffic',         'City Traffic API'),
 (2,  2,  '2026-11-01 07:31', 'weather',      1, 'Light rain',                          'Open-Meteo'),
 (3,  3,  '2026-11-01 08:11', 'construction', 3, 'Lane reduction near Adelaide Avenue', 'City Traffic API'),
 (4,  4,  '2026-11-01 08:11', 'traffic',      1, 'Transit operating on schedule',       'DRT Feed'),
 (5,  5,  '2026-11-02 12:01', 'weather',      0, 'Clear and dry',                       'Open-Meteo'),
 (6,  6,  '2026-11-02 12:01', 'traffic',      2, 'Lunch-hour congestion',               'City Traffic API'),
 (7,  7,  '2026-11-03 16:01', 'traffic',      4, 'Heavy Highway 401 congestion',        'City Traffic API'),
 (8,  8,  '2026-11-03 16:01', 'weather',      2, 'Strong wind',                         'Open-Meteo'),
 (9,  9,  '2026-11-04 09:01', 'weather',      1, 'Cool and dry',                        'Open-Meteo'),
 (10, 10, '2026-11-04 09:01', 'construction', 2, 'Trail maintenance',                   'City Open Data'),
 (11, 11, '2026-11-05 17:01', 'traffic',      1, 'Minor delay',                         'DRT Feed'),
 (12, 12, '2026-11-05 17:01', 'closure',      3, 'Temporary ramp closure',              'City Traffic API');

INSERT INTO saved_location
 (saved_location_id, user_id, location_id, label, is_favourite, saved_at) VALUES
 (1, 1, 1, 'Campus',     TRUE,  '2026-10-21 09:00'),
 (2, 2, 2, 'Shopping',   FALSE, '2026-10-22 10:00'),
 (3, 3, 4, 'Hospital',   TRUE,  '2026-10-23 11:00'),
 (4, 4, 6, 'GO Station', TRUE,  '2026-10-24 12:00'),
 (5, 5, 7, 'Park',       TRUE,  '2026-10-25 13:00'),
 (6, 6, 8, 'College',    FALSE, '2026-10-26 14:00');

INSERT INTO feedback
 (feedback_id, user_id, trip_id, rating, comments, submitted_at) VALUES
 (1, 1, 1, 5, 'Fast route and accurate estimate.',  '2026-11-01 09:00'),
 (2, 2, 2, 4, 'Transit option was convenient.',     '2026-11-01 10:00'),
 (3, 3, 3, 5, 'Safe cycling route.',                '2026-11-02 14:00'),
 (4, 4, 4, 3, 'Traffic made the trip slower.',      '2026-11-03 18:00'),
 (5, 1, 3, 4, 'Useful alternative comparison.',     '2026-11-04 15:00'),
 (6, 2, 1, 4, 'The condition warning was helpful.', '2026-11-05 16:00');

-- Phase III correction: explicit IDs do not advance identity sequences in
-- PostgreSQL, so advance each sequence past the highest seeded key.
SELECT setval(pg_get_serial_sequence('app_user', 'user_id'),                   (SELECT MAX(user_id) FROM app_user));
SELECT setval(pg_get_serial_sequence('location', 'location_id'),               (SELECT MAX(location_id) FROM location));
SELECT setval(pg_get_serial_sequence('user_preference', 'preference_id'),      (SELECT MAX(preference_id) FROM user_preference));
SELECT setval(pg_get_serial_sequence('trip', 'trip_id'),                       (SELECT MAX(trip_id) FROM trip));
SELECT setval(pg_get_serial_sequence('route_option', 'route_id'),              (SELECT MAX(route_id) FROM route_option));
SELECT setval(pg_get_serial_sequence('route_segment', 'segment_id'),           (SELECT MAX(segment_id) FROM route_segment));
SELECT setval(pg_get_serial_sequence('condition_observation', 'observation_id'), (SELECT MAX(observation_id) FROM condition_observation));
SELECT setval(pg_get_serial_sequence('saved_location', 'saved_location_id'),   (SELECT MAX(saved_location_id) FROM saved_location));
SELECT setval(pg_get_serial_sequence('feedback', 'feedback_id'),               (SELECT MAX(feedback_id) FROM feedback));

COMMIT;
