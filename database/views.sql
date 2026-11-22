-- =====================================================================
-- Intelligent Route Planning System — the ten Phase II views (Part C)
--
-- SQL bodies are reproduced from the Phase II report unchanged and were
-- verified on PostgreSQL 16 (see docs/TEST_RESULTS.md).  CREATE OR REPLACE
-- is used so this file can be re-applied safely.
-- =====================================================================

-- View 1: join of five tables (trip, app_user, location x2, route_option).
CREATE OR REPLACE VIEW v1_trip_route_details AS
SELECT
    t.trip_id,
    u.full_name,
    origin.location_name AS origin,
    destination.location_name AS destination,
    r.route_id,
    r.travel_mode,
    r.distance_km,
    r.estimated_duration_min,
    r.is_selected
FROM trip AS t
JOIN app_user AS u ON u.user_id = t.user_id
JOIN location AS origin ON origin.location_id = t.origin_location_id
JOIN location AS destination ON destination.location_id = t.destination_location_id
JOIN route_option AS r ON r.trip_id = t.trip_id;

-- View 2: nested query with ALL over a GROUP BY subquery.
CREATE OR REPLACE VIEW v2_faster_than_all_mode_averages AS
SELECT
    r.route_id,
    r.trip_id,
    r.travel_mode,
    r.estimated_duration_min
FROM route_option AS r
WHERE r.estimated_duration_min < ALL (
    SELECT AVG(r2.estimated_duration_min)
    FROM route_option AS r2
    GROUP BY r2.travel_mode
);

-- View 3: correlated nested query (average of the route's own trip).
CREATE OR REPLACE VIEW v3_faster_than_trip_average AS
SELECT
    r.route_id,
    r.trip_id,
    r.travel_mode,
    r.estimated_duration_min
FROM route_option AS r
WHERE r.estimated_duration_min < (
    SELECT AVG(r2.estimated_duration_min)
    FROM route_option AS r2
    WHERE r2.trip_id = r.trip_id
);

-- View 4: FULL JOIN preserving users without feedback.
CREATE OR REPLACE VIEW v4_users_and_feedback AS
SELECT
    u.user_id,
    u.full_name,
    f.feedback_id,
    f.trip_id,
    f.rating,
    f.comments
FROM app_user AS u
FULL JOIN feedback AS f ON f.user_id = u.user_id;

-- View 5: nested query using the UNION set operation.
CREATE OR REPLACE VIEW v5_relevant_locations AS
SELECT
    l.location_id,
    l.location_name,
    l.city,
    l.location_type
FROM location AS l
WHERE l.location_id IN (
    SELECT sl.location_id
    FROM saved_location AS sl
    UNION
    SELECT t.destination_location_id
    FROM trip AS t
);

-- View 6: weighted route recommendation (CTEs + window functions).
-- Weights: time 45%, distance 25%, condition safety 15%, toll cost 10%, preference match 5%.
CREATE OR REPLACE VIEW v6_ranked_route_recommendations AS
WITH route_risk AS (
    SELECT
        r.route_id,
        COALESCE(MAX(c.severity), 0) AS max_severity
    FROM route_option AS r
    LEFT JOIN route_segment AS s ON s.route_id = r.route_id
    LEFT JOIN condition_observation AS c ON c.segment_id = s.segment_id
    GROUP BY r.route_id
),
scored AS (
    SELECT
        r.route_id,
        r.trip_id,
        r.travel_mode,
        r.distance_km,
        r.estimated_duration_min,
        r.toll_cost,
        ROUND(100.0 * MIN(r.estimated_duration_min) OVER (PARTITION BY r.trip_id)
              / r.estimated_duration_min, 2) AS time_score,
        ROUND(100.0 * MIN(r.distance_km) OVER (PARTITION BY r.trip_id)
              / r.distance_km, 2) AS distance_score,
        (100 - rr.max_severity * 20)::NUMERIC AS safety_score,
        GREATEST(0, 100 - r.toll_cost * 20)::NUMERIC AS toll_score,
        CASE WHEN r.travel_mode = p.preferred_mode THEN 100::NUMERIC ELSE 50::NUMERIC END AS preference_score
    FROM route_option AS r
    JOIN trip AS t ON t.trip_id = r.trip_id
    JOIN user_preference AS p ON p.user_id = t.user_id
    JOIN route_risk AS rr ON rr.route_id = r.route_id
)
SELECT
    route_id,
    trip_id,
    travel_mode,
    distance_km,
    estimated_duration_min,
    time_score,
    distance_score,
    safety_score,
    toll_score,
    preference_score,
    ROUND(
        0.45 * time_score
      + 0.25 * distance_score
      + 0.15 * safety_score
      + 0.10 * toll_score
      + 0.05 * preference_score,
        2
    ) AS total_route_score,
    DENSE_RANK() OVER (
        PARTITION BY trip_id
        ORDER BY (
            0.45 * time_score
          + 0.25 * distance_score
          + 0.15 * safety_score
          + 0.10 * toll_score
          + 0.05 * preference_score
        ) DESC
    ) AS recommendation_rank
FROM scored;

-- View 7: condition risk per route (LEFT JOIN + aggregation).
CREATE OR REPLACE VIEW v7_condition_risk_by_route AS
SELECT
    r.route_id,
    r.trip_id,
    COUNT(c.observation_id) AS observation_count,
    COALESCE(ROUND(AVG(c.severity), 2), 0) AS average_severity,
    COALESCE(MAX(c.severity), 0) AS maximum_severity
FROM route_option AS r
LEFT JOIN route_segment AS s ON s.route_id = r.route_id
LEFT JOIN condition_observation AS c ON c.segment_id = s.segment_id
GROUP BY r.route_id, r.trip_id;

-- View 8: favourite saved places (three-table join).
CREATE OR REPLACE VIEW v8_favourite_saved_locations AS
SELECT
    u.user_id,
    u.full_name,
    sl.label,
    l.location_name,
    l.street_address,
    l.city
FROM saved_location AS sl
JOIN app_user AS u ON u.user_id = sl.user_id
JOIN location AS l ON l.location_id = sl.location_id
WHERE sl.is_favourite = TRUE;

-- View 9: low-carbon, no-toll alternatives.
CREATE OR REPLACE VIEW v9_low_carbon_alternatives AS
SELECT
    r.route_id,
    r.trip_id,
    r.travel_mode,
    r.distance_km,
    r.estimated_duration_min
FROM route_option AS r
WHERE r.travel_mode IN ('walking', 'cycling', 'transit')
  AND r.toll_cost = 0;

-- View 10: feedback summary per user (LEFT JOIN + aggregation).
CREATE OR REPLACE VIEW v10_user_feedback_summary AS
SELECT
    u.user_id,
    u.full_name,
    COUNT(f.feedback_id) AS feedback_count,
    ROUND(AVG(f.rating), 2) AS average_rating,
    MAX(f.submitted_at) AS most_recent_feedback
FROM app_user AS u
LEFT JOIN feedback AS f ON f.user_id = u.user_id
GROUP BY u.user_id, u.full_name;
