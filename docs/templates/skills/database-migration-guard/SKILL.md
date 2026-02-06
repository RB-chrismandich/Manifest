---
name: database-migration-guard
description: |
  Auto-trigger when detecting database migration files or schema changes.
  Validates migration safety and backwards compatibility without blocking user flow.
---

# Database Migration Guard Skill

This skill automatically activates when Claude detects changes to database schema or migration files.

## Trigger Criteria

### Migration File Patterns (Immediate Trigger)

Activate when files matching these patterns are modified:

**Django (Python)**:

- `*/migrations/*.py`
- `models.py` files

**SQLAlchemy (Python)**:

- `*/alembic/versions/*.py`
- `alembic/env.py`

**Rails (Ruby)**:

- `db/migrate/*.rb`
- `db/schema.rb`

**Node.js (Sequelize, Knex, TypeORM)**:

- `*/migrations/*.js`, `*/migrations/*.ts`
- `*/models/*.js`, `*/models/*.ts`

**Go (golang-migrate, GORM)**:

- `*/migrations/*.sql`
- `*/migrations/*.go`

## Behavior

When triggered, this skill performs lightweight validation:

1. **Check migration safety** - Breaking vs non-breaking changes
2. **Check backwards compatibility** - Can old code run with new schema?
3. **Check data migration** - Is there a plan for existing data?
4. **Check rollback strategy** - Can this migration be reversed?
5. **Check index strategy** - Large tables use CONCURRENT index creation
6. **Report inline** - Non-blocking feedback

## Analysis Checks

### 1. Breaking vs Non-Breaking Changes

**Non-breaking (safe to deploy immediately)**:

- ✅ Add new table
- ✅ Add new column (with DEFAULT or NULL)
- ✅ Add new index (CONCURRENTLY for PostgreSQL)
- ✅ Add new constraint (NOT VALID, then validate separately)

**Breaking (requires multi-phase deployment)**:

- ⚠️ Rename column (needs dual-write period)
- ⚠️ Remove column (needs dual-read period first)
- ⚠️ Change column type (needs backfill)
- ⚠️ Add NOT NULL constraint without DEFAULT
- ❌ Remove table (must ensure no code references it)

**Check**: Flag breaking changes and recommend multi-phase approach.

### 2. Backwards Compatibility

Verify that old application code can run with the new schema:

**Good example** (backwards compatible):

```python
# Migration: Add new column with DEFAULT
class Migration:
    def upgrade():
        op.add_column('users', sa.Column('age', sa.Integer(), nullable=True, server_default='0'))
```

Old code doesn't know about `age` column → still works ✅

**Bad example** (breaks old code):

```python
# Migration: Add NOT NULL column without DEFAULT
class Migration:
    def upgrade():
        op.add_column('users', sa.Column('age', sa.Integer(), nullable=False))
```

Old code tries to INSERT without `age` → fails ❌

**Multi-phase approach** for breaking changes:

```python
# Phase 1: Add nullable column
op.add_column('users', sa.Column('age', sa.Integer(), nullable=True))

# Deploy new code that writes to both old and new columns

# Phase 2: Backfill data
op.execute('UPDATE users SET age = 0 WHERE age IS NULL')

# Deploy new code that only uses new column

# Phase 3: Make NOT NULL
op.alter_column('users', 'age', nullable=False)

# Phase 4: Remove old column (if any)
op.drop_column('users', 'old_age_field')
```

**Check**:

- New columns are nullable or have defaults
- Renamed/removed columns use multi-phase approach
- Migration comments explain phasing

### 3. Data Migration Strategy

For migrations that transform existing data:

**Required elements**:

- Data backfill script
- Rollback plan
- Performance estimate (for large tables)
- Batching strategy (for >100k rows)

**Good example**:

```python
# Migration: Normalize phone numbers
class Migration:
    def upgrade():
        # 1. Add new column
        op.add_column('users', sa.Column('phone_normalized', sa.String(20), nullable=True))

        # 2. Backfill in batches
        batch_size = 1000
        op.execute('''
            UPDATE users
            SET phone_normalized = regexp_replace(phone, '[^0-9]', '', 'g')
            WHERE id IN (
                SELECT id FROM users
                WHERE phone_normalized IS NULL
                LIMIT {batch_size}
            )
        '''.format(batch_size=batch_size))

        # 3. Make NOT NULL after backfill
        op.alter_column('users', 'phone_normalized', nullable=False)

    def downgrade():
        op.drop_column('users', 'phone_normalized')
```

**Check**:

- Batching used for large tables
- Rollback script provided
- Data transformation logic tested

### 4. Index Creation Strategy

For large tables (>100k rows), use concurrent index creation to avoid locking:

**PostgreSQL - Good**:

```sql
CREATE INDEX CONCURRENTLY idx_users_email ON users(email);
```

**PostgreSQL - Bad** (locks table during creation):

```sql
CREATE INDEX idx_users_email ON users(email);
```

**MySQL - Good**:

```sql
ALTER TABLE users ADD INDEX idx_users_email (email), ALGORITHM=INPLACE, LOCK=NONE;
```

**Check**:

- Large tables (>100k rows) use CONCURRENT or ONLINE options
- Migration comments note expected index creation time

### 5. Constraint Safety

Adding constraints requires care to avoid locking tables:

**PostgreSQL - Good** (two-phase approach):

```sql
-- Phase 1: Add constraint as NOT VALID (no table scan, fast)
ALTER TABLE users ADD CONSTRAINT users_email_check CHECK (email ~* '@') NOT VALID;

-- Phase 2: Validate in separate transaction (can be cancelled if needed)
ALTER TABLE users VALIDATE CONSTRAINT users_email_check;
```

**PostgreSQL - Bad** (locks table during full scan):

```sql
ALTER TABLE users ADD CONSTRAINT users_email_check CHECK (email ~* '@');
```

**Check**:

- NOT NULL constraints have DEFAULT values
- CHECK constraints use NOT VALID + VALIDATE pattern
- Foreign keys use NOT VALID + VALIDATE pattern

### 6. Rollback Strategy

Every migration should have a tested rollback plan:

**Required**:

- `downgrade()` or `down()` function implemented
- Rollback tested on staging
- Data loss risk documented (if any)

**Example**:

```python
class Migration:
    def upgrade():
        op.add_column('users', sa.Column('age', sa.Integer(), nullable=True))

    def downgrade():
        # SAFE: Column removal doesn't break old code
        # WARNING: Data in 'age' column will be lost
        op.drop_column('users', 'age')
```

**Check**:

- Downgrade function present
- Data loss risk documented
- Rollback tested

## Validation Output

```text
🗄️ Database Migration Guard Findings:

Migration: 20260204_add_user_age.py

✅ Backwards compatibility: PASS
   - New column 'age' is nullable
   - Old code can run with new schema

⚠️  Data migration: WARNING
   - No backfill script for existing rows
   - Recommendation: Add default value or backfill script

✅ Index strategy: PASS
   - Using CREATE INDEX CONCURRENTLY
   - Estimated time: 30s for 500k rows

❌ Rollback: FAIL
   - No downgrade() function
   - Add rollback script before deploying

Deployment recommendation: MULTI-PHASE
  Phase 1: Deploy migration (add nullable column)
  Phase 2: Deploy code that writes to new column
  Phase 3: Backfill existing data
  Phase 4: Make column NOT NULL (if needed)
```

## Common Patterns

### Safe Column Rename (3-phase)

```python
# Phase 1: Add new column, dual-write
op.add_column('users', sa.Column('full_name', sa.String(), nullable=True))
# Deploy code that writes to both 'name' and 'full_name'

# Phase 2: Backfill
op.execute('UPDATE users SET full_name = name WHERE full_name IS NULL')
# Deploy code that reads from 'full_name', writes to both

# Phase 3: Remove old column
op.drop_column('users', 'name')
# Deploy code that only uses 'full_name'
```

### Safe Column Removal (2-phase)

```python
# Phase 1: Stop writing to column
# Deploy code that doesn't write to 'deprecated_field'

# Phase 2: Remove column
op.drop_column('users', 'deprecated_field')
# Verify no code references the field
```

### Safe Type Change (4-phase)

```python
# Phase 1: Add new column
op.add_column('users', sa.Column('age_int', sa.Integer(), nullable=True))

# Phase 2: Dual-write
# Deploy code that writes to both 'age' (string) and 'age_int' (integer)

# Phase 3: Backfill
op.execute('UPDATE users SET age_int = CAST(age AS INTEGER) WHERE age_int IS NULL')
# Deploy code that reads from 'age_int', writes to both

# Phase 4: Remove old column
op.drop_column('users', 'age')
```

## Configuration

```yaml
skills:
  database-migration-guard:
    enabled: true
    large_table_threshold: 100000  # Rows
    require_concurrent_indexes: true
    require_rollback: true
```

## Related

- `templates/skills/api-security-guard` - API endpoint validation
- `templates/validation-overrides/database-safety.yml` - Database-specific rules
