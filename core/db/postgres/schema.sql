-- ============================================
-- PostgreSQL schema for UGR Matrix Bot
-- ============================================

-- Users table 
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    matrix_id TEXT UNIQUE NOT NULL,        -- Matrix user ID
    moodle_id INTEGER UNIQUE NOT NULL,     -- Moodle user ID
    is_teacher BOOLEAN DEFAULT FALSE,      -- true = teacher, false = student
    registered_at TIMESTAMP DEFAULT NOW()
);

-- 🔹 Index for fast lookup by Matrix ID
CREATE INDEX IF NOT EXISTS idx_users_matrix_id ON users(matrix_id);


-- Chat rooms table
CREATE TABLE IF NOT EXISTS rooms (
    id SERIAL PRIMARY KEY,
    room_id TEXT UNIQUE NOT NULL,          -- Actual Matrix room ID
    moodle_course_id INTEGER NOT NULL,     -- Moodle course ID
    teacher_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    shortcode TEXT NOT NULL,               -- short identifier used by the teacher
    moodle_group TEXT,                     -- optional Moodle group, if present only that group has access
    created_at TIMESTAMP DEFAULT NOW(),
    active BOOLEAN DEFAULT TRUE,           -- whether the room is active
    UNIQUE (teacher_id, shortcode)         -- shortcode unique per teacher
);

-- 🔹 Index for fast lookup by Matrix room ID
CREATE INDEX IF NOT EXISTS idx_rooms_room_id ON rooms(room_id);

-- 🔹 Index for quick lookup by (teacher, shortcode)
CREATE INDEX IF NOT EXISTS idx_rooms_teacher_shortcode ON rooms(teacher_id, shortcode);


-- Reactions table (teacher → student in a course)
CREATE TABLE IF NOT EXISTS reactions (
    id SERIAL PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    emoji TEXT NOT NULL,                   -- reaction emoji ("👍", etc.)
    count INTEGER DEFAULT 1 CHECK (count >= 1),
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE (teacher_id, student_id, room_id, emoji)
);

-- 🔹 Indexes for faster joins and lookups
CREATE INDEX IF NOT EXISTS idx_reactions_teacher_id ON reactions(teacher_id);
CREATE INDEX IF NOT EXISTS idx_reactions_student_id ON reactions(student_id);
CREATE INDEX IF NOT EXISTS idx_reactions_room_id ON reactions(room_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'weekday'
    ) THEN
        CREATE TYPE weekday AS ENUM (
            'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'
        );
    END IF;
END
$$;

-- Teacher availability table
CREATE TABLE IF NOT EXISTS teacher_availability (
    id SERIAL PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day_of_week weekday NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    CONSTRAINT chk_time_valid CHECK (start_time < end_time)
    );

-- 🔹 Index for fast lookup by teacher ID
CREATE INDEX IF NOT EXISTS idx_teacher_availability_teacher_id ON teacher_availability(teacher_id);

-- 🔹 Trigger to prevent overlapping intervals for the same teacher
CREATE OR REPLACE FUNCTION trg_no_overlap_func()
RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM teacher_availability
        WHERE teacher_id = NEW.teacher_id
          AND day_of_week = NEW.day_of_week
          AND NEW.start_time < end_time
          AND NEW.end_time > start_time
    ) THEN
        RAISE EXCEPTION 'Time interval overlaps with existing interval for this teacher';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_no_overlap'
    ) THEN
        CREATE TRIGGER trg_no_overlap
        BEFORE INSERT ON teacher_availability
        FOR EACH ROW
        EXECUTE FUNCTION trg_no_overlap_func();
    END IF;
END
$$;

-- ============================================