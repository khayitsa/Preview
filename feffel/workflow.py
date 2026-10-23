"""Approval workflows.

A company's workflow is a list of stages. Each stage names a role, may depend on other stages,
and needs approval from any one eligible reviewer (``mode: any``) or every one (``mode: all``).
The workflow in force is copied onto a post when it is submitted, together with the list of
eligible reviewers, so later changes to roles do not rewrite past decisions.
"""

import json
import re

from . import constants
from .access import permissions, visible
from .errors import require, textval

STAGE_ID = re.compile(r'[a-zA-Z0-9_-]{1,64}')


def default_workflow(roles):
    """The starting workflow for a new organisation. ``roles`` maps role name to id."""
    return [
        {
            'id': 'creative',
            'name': 'Creative review',
            'role': roles['Head of Creative'],
            'depends': [],
            'mode': 'any',
            'allow_self': True,
        },
        {
            'id': 'marketing',
            'name': 'Marketing review',
            'role': roles['Head of Marketing'],
            'depends': [],
            'mode': 'any',
            'allow_self': True,
        },
        {
            'id': 'brand',
            'name': 'Final brand approval',
            'role': roles[constants.ADMIN_ROLE],
            'depends': ['creative', 'marketing'],
            'mode': 'any',
            'allow_self': True,
        },
    ]


def validate_workflow(db, org, stages):
    """Check a submitted workflow and return it normalised. Raises ``Error`` (400) if invalid."""
    require(isinstance(stages, list) and 1 <= len(stages) <= 20, 'Add between 1 and 20 review stages', 400)
    ids = [s.get('id') for s in stages]
    require(
        all(isinstance(i, str) and STAGE_ID.fullmatch(i) for i in ids) and len(set(ids)) == len(ids),
        'Stage IDs must be unique',
        400,
    )
    result = []
    for stage in stages:
        require(
            db.execute('SELECT 1 FROM roles WHERE id=? AND org=?', (stage.get('role'), org)).fetchone(),
            'Unknown reviewer role',
            400,
        )
        role = db.execute('SELECT permissions FROM roles WHERE id=?', (stage['role'],)).fetchone()
        require('review' in json.loads(role[0]), 'Reviewer roles need the review permission', 400)
        depends = stage.get('depends', [])
        require(
            isinstance(depends, list) and all(d in ids and d != stage['id'] for d in depends),
            'Invalid stage dependencies',
            400,
        )
        require(stage.get('mode', 'any') in ['any', 'all'], 'Invalid approval mode', 400)
        result.append(
            {
                'id': stage['id'],
                'name': textval(stage.get('name', ''), 100),
                'role': stage['role'],
                'depends': depends,
                'mode': stage.get('mode', 'any'),
                'allow_self': bool(stage.get('allow_self', True)),
            }
        )
    _reject_cycles({s['id']: s['depends'] for s in result}, ids)
    return result


def _reject_cycles(graph, ids):
    visited, active = set(), set()

    def visit(node):
        require(node not in active, 'Approval dependencies contain a cycle', 400)
        if node not in visited:
            active.add(node)
            for dependency in graph[node]:
                visit(dependency)
            active.remove(node)
            visited.add(node)

    for node in ids:
        visit(node)


def _approvals_by_stage(db, post, stages):
    """Users who currently approve each stage of this version (an 'undo' withdraws an approval)."""
    approvals = {s['id']: set() for s in stages}
    rows = db.execute(
        'SELECT * FROM decisions WHERE post=? AND version=? ORDER BY created,rowid',
        (post['id'], post['version']),
    )
    for decision in rows:
        if decision['stage'] not in approvals:
            continue
        if decision['action'] == 'approve':
            approvals[decision['stage']].add(decision['user'])
        elif decision['action'] == 'undo':
            approvals[decision['stage']].discard(decision['user'])
    return approvals


def stage_state(db, post, user):
    """Progress of every stage for ``user``'s view of ``post``.

    Each returned stage carries ``eligible`` reviewers, who has approved, whether it is ``done``
    or ``ready`` (all dependencies done) and whether ``user`` ``can_approve`` it right now.
    """
    stages = json.loads(post['workflow'])
    approvals = _approvals_by_stage(db, post, stages)
    members = db.execute('SELECT * FROM members WHERE org=?', (post['org'],)).fetchall()
    active_reviewers = {m['user'] for m in members if visible(m, post) and 'review' in permissions(db, m)}
    states, completed, pending = [], set(), list(stages)
    for _ in stages:
        for stage in list(pending):
            if not all(d in {s['id'] for s in states} for d in stage['depends']):
                continue
            # Posts under review carry the reviewer list captured at submission.
            eligible = stage.get(
                'reviewers',
                [
                    m['user']
                    for m in members
                    if m['role'] == stage['role']
                    and visible(m, post)
                    and (stage['allow_self'] or m['user'] != post['creator'])
                ],
            )
            approved_by = approvals[stage['id']] & set(eligible)
            if stage['mode'] == 'any':
                done = bool(approved_by)
            else:
                done = bool(eligible) and set(eligible) <= approved_by
            if not set(stage['depends']) <= completed:
                done = False
            if done:
                completed.add(stage['id'])
            ready = set(stage['depends']) <= completed
            states.append(
                {
                    **stage,
                    'eligible': eligible,
                    'approved_by': list(approved_by),
                    'done': done,
                    'ready': ready,
                    'can_approve': (
                        ready
                        and not done
                        and user in eligible
                        and user in active_reviewers
                        and post['status'] == 'review'
                    ),
                    'blocked_empty': not eligible,
                }
            )
            pending.remove(stage)
    by_id = {s['id']: s for s in states}
    return [by_id[s['id']] for s in stages]
