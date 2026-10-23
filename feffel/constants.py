"""Fixed vocabulary of the application: platforms, permissions, default roles, limits.

Deployment settings (paths, URLs, limits that operators change) live in ``config.py`` instead.
"""

SESSION_COOKIE = 'feffel_session'
SESSION_SECONDS = 7 * 86400
INVITE_SECONDS = 7 * 86400
VERSION = '1.0.0'

#: Content formats offered by each platform.
PLATFORMS = {
    'instagram': ['Photo', 'Carousel', 'Reel', 'Story'],
    'facebook': ['Text', 'Photo', 'Carousel', 'Video', 'Reel', 'Story'],
    'linkedin': ['Text', 'Photo', 'Carousel', 'Video', 'PDF document'],
    'x': ['Text', 'Photo', 'Carousel', 'Video'],
    'tiktok': ['Video', 'Photo carousel', 'Story'],
    'youtube': ['Video', 'Short', 'Community post'],
    'pinterest': ['Image pin', 'Video pin'],
    'threads': ['Text', 'Photo', 'Carousel', 'Video'],
}

#: Every permission a role can hold.
PERMISSIONS = ['create', 'edit_all', 'review', 'manage', 'override', 'export', 'archive']

#: Roles created for each new organisation.
ADMIN_ROLE = 'Head of Brand & Client Experience'
DEFAULT_ROLES = [
    ('Creative Assistant', ['create', 'export']),
    ('Creative Lead', ['create', 'edit_all', 'export']),
    ('Head of Creative', ['create', 'edit_all', 'review', 'export']),
    ('Head of Marketing', ['create', 'edit_all', 'review', 'export']),
    ('Legal Reviewer', ['review', 'export']),
    (ADMIN_ROLE, PERMISSIONS),
    ('Viewer', []),
]

REACTIONS = ['❤️', '👍', '💡', '🔥', '']
TASK_KINDS = ['Creative', 'Marketing', 'Legal', 'Other']
TASK_STATUSES = ['todo', 'doing', 'done']
MAX_ASSETS_PER_POST = 35
MAX_JSON_BYTES = 2 * 1024 * 1024
