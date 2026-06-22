PRAGMA user_version = 2;
CREATE TABLE applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, company TEXT NOT NULL, location TEXT DEFAULT '',
    url TEXT DEFAULT '', salary_text TEXT DEFAULT '', source TEXT DEFAULT 'manual',
    status TEXT DEFAULT 'interested', date_added TEXT NOT NULL,
    date_applied TEXT DEFAULT '', notes TEXT DEFAULT ''
);
CREATE TABLE inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    norm_url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL, company TEXT NOT NULL, location TEXT DEFAULT '',
    url TEXT DEFAULT '', salary_text TEXT DEFAULT '', description TEXT DEFAULT '',
    source TEXT DEFAULT '', score INTEGER DEFAULT -1, score_notes TEXT DEFAULT '',
    fit INTEGER DEFAULT -1, fit_why TEXT DEFAULT '', created TEXT DEFAULT '',
    date_added TEXT NOT NULL, board_count INTEGER DEFAULT -1
);
INSERT INTO inbox (norm_url, title, company, location, url, salary_text,
    description, source, score, fit, created, date_added)
VALUES ('x.co/1', 'Software Developer', 'Acme', 'Cincinnati, OH',
    'https://x.co/1', '$120k', 'controls', 'adzuna', 70, -1,
    '2026-06-20', '2026-06-20');
