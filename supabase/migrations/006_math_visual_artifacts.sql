-- Migration 006: Add visualization columns to math_blocks
-- Stores ManimGL-generated visual URLs and the scene code used to produce them.

ALTER TABLE math_blocks
  ADD COLUMN IF NOT EXISTS viz_image_url TEXT,
  ADD COLUMN IF NOT EXISTS viz_video_url TEXT,
  ADD COLUMN IF NOT EXISTS viz_manim_code TEXT;
