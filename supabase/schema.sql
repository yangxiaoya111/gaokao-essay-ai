-- ============================================================
-- 高考满分作文智能应用 —— Supabase 数据库结构
-- 使用方法：在 Supabase 控制台 → SQL Editor 中粘贴并执行本文件
-- ============================================================

create extension if not exists "pgcrypto";

-- 用户表
create table if not exists users (
  id            uuid primary key default gen_random_uuid(),
  username      text unique not null,
  password_hash text not null,
  created_at    timestamptz default now()
);

-- 会话表（登录令牌）
create table if not exists sessions (
  token      text primary key,
  user_id    uuid references users(id) on delete cascade,
  created_at timestamptz default now(),
  expires_at timestamptz not null
);

-- 作文历史表
create table if not exists essays (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid references users(id) on delete cascade,
  topic      text not null,
  style      text,
  title      text,
  content    text,
  char_count integer,
  created_at timestamptz default now()
);

-- 索引
create index if not exists idx_essays_user    on essays(user_id, created_at desc);
create index if not exists idx_sessions_expiry on sessions(expires_at);

-- 说明：本应用通过服务端的 SUPABASE_SERVICE_ROLE_KEY 访问数据库，
-- 该密钥拥有完全权限且绕过行级安全（RLS），请勿在前端代码中暴露。
