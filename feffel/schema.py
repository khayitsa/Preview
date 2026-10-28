"""Database schema. Statements are idempotent so they run on every start."""

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS users(
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        name TEXT NOT NULL,
        password TEXT NOT NULL,
        created TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS orgs(
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roles(
        id TEXT PRIMARY KEY,
        org TEXT NOT NULL REFERENCES orgs(id),
        name TEXT NOT NULL,
        permissions TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS members(
        id TEXT PRIMARY KEY,
        org TEXT NOT NULL REFERENCES orgs(id),
        user TEXT NOT NULL REFERENCES users(id),
        role TEXT NOT NULL REFERENCES roles(id),
        companies TEXT NOT NULL DEFAULT '[]',
        platforms TEXT NOT NULL DEFAULT '[]',
        title TEXT NOT NULL DEFAULT '',
        UNIQUE(org,user)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS companies(
        id TEXT PRIMARY KEY,
        org TEXT NOT NULL REFERENCES orgs(id),
        name TEXT NOT NULL,
        handle TEXT NOT NULL,
        color TEXT NOT NULL,
        workflow TEXT NOT NULL,
        accounts TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions(
        token TEXT PRIMARY KEY,
        user TEXT NOT NULL REFERENCES users(id),
        csrf TEXT NOT NULL,
        expires REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS invites(
        id TEXT PRIMARY KEY,
        org TEXT NOT NULL REFERENCES orgs(id),
        email TEXT NOT NULL,
        role TEXT NOT NULL REFERENCES roles(id),
        companies TEXT NOT NULL,
        platforms TEXT NOT NULL,
        title TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE,
        expires REAL NOT NULL,
        used INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS password_resets(
        id TEXT PRIMARY KEY,
        user TEXT NOT NULL REFERENCES users(id),
        token_hash TEXT NOT NULL UNIQUE,
        expires REAL NOT NULL,
        used INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assets(
        id TEXT PRIMARY KEY,
        org TEXT NOT NULL REFERENCES orgs(id),
        user TEXT NOT NULL REFERENCES users(id),
        name TEXT NOT NULL,
        mime TEXT NOT NULL,
        size INTEGER NOT NULL,
        created TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS posts(
        id TEXT PRIMARY KEY,
        org TEXT NOT NULL REFERENCES orgs(id),
        company TEXT NOT NULL REFERENCES companies(id),
        creator TEXT NOT NULL REFERENCES users(id),
        platform TEXT NOT NULL,
        format TEXT NOT NULL,
        title TEXT NOT NULL,
        caption TEXT NOT NULL,
        assets TEXT NOT NULL,
        scheduled TEXT NOT NULL DEFAULT '',
        historical INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        lock INTEGER NOT NULL DEFAULT 1,
        workflow TEXT NOT NULL,
        created TEXT NOT NULL,
        updated TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS revisions(
        id TEXT PRIMARY KEY,
        post TEXT NOT NULL REFERENCES posts(id),
        version INTEGER NOT NULL,
        data TEXT NOT NULL,
        user TEXT NOT NULL REFERENCES users(id),
        created TEXT NOT NULL,
        UNIQUE(post,version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS decisions(
        id TEXT PRIMARY KEY,
        post TEXT NOT NULL REFERENCES posts(id),
        version INTEGER NOT NULL,
        stage TEXT NOT NULL,
        user TEXT NOT NULL REFERENCES users(id),
        action TEXT NOT NULL,
        note TEXT NOT NULL,
        created TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comments(
        id TEXT PRIMARY KEY,
        post TEXT NOT NULL REFERENCES posts(id),
        version INTEGER NOT NULL,
        user TEXT NOT NULL REFERENCES users(id),
        body TEXT NOT NULL,
        context TEXT NOT NULL,
        resolved INTEGER NOT NULL DEFAULT 0,
        parent TEXT,
        created TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tasks(
        id TEXT PRIMARY KEY,
        post TEXT NOT NULL REFERENCES posts(id),
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        assignee TEXT,
        status TEXT NOT NULL,
        notes TEXT NOT NULL,
        due TEXT NOT NULL,
        created TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reactions(
        post TEXT NOT NULL REFERENCES posts(id),
        user TEXT NOT NULL REFERENCES users(id),
        emoji TEXT NOT NULL,
        PRIMARY KEY(post,user)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS notifications(
        id TEXT PRIMARY KEY,
        org TEXT NOT NULL REFERENCES orgs(id),
        user TEXT NOT NULL REFERENCES users(id),
        post TEXT,
        body TEXT NOT NULL,
        seen INTEGER NOT NULL DEFAULT 0,
        created TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit(
        id TEXT PRIMARY KEY,
        org TEXT NOT NULL REFERENCES orgs(id),
        post TEXT,
        user TEXT NOT NULL REFERENCES users(id),
        event TEXT NOT NULL,
        detail TEXT NOT NULL,
        created TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS mail_outbox(
        id TEXT PRIMARY KEY,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        created TEXT NOT NULL,
        sent TEXT,
        error TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rate_limits(
        key TEXT PRIMARY KEY,
        window REAL NOT NULL,
        count INTEGER NOT NULL
    )
    """,
]

INDEXES = [
    'CREATE INDEX IF NOT EXISTS idx_posts_org ON posts(org,company,platform)',
    'CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post,version)',
    'CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user,org)',
]

#: Columns added after the first release. ``init_db`` adds them to older databases.
LATE_COLUMNS = {
    'members': ['department', 'reports_to'],
    'invites': ['department', 'reports_to'],
}
