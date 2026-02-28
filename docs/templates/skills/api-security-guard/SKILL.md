---
name: api-security-guard
description: |
  Auto-trigger when detecting modifications to API endpoints, request handlers,
  authentication middleware, or input validation code.
  Validates API security best practices without blocking user flow.
---

# API Security Guard Skill

This skill automatically activates when Claude detects changes to API-related code.

## Trigger Criteria

### HTTP Endpoint Patterns (Immediate Trigger)

Activate when code modifications touch any of these patterns:

**Express.js (Node.js)**:

- `app.get(`, `app.post(`, `app.put(`, `app.delete(`, `app.patch(`
- `router.get(`, `router.post(`, etc.
- `express.Router()`
- `req.params`, `req.query`, `req.body`

**Django (Python)**:

- `@api_view`
- `class.*APIView`, `class.*ViewSet`
- `request.GET`, `request.POST`, `request.data`
- `serializers.`, `Serializer`

**FastAPI (Python)**:

- `@app.get(`, `@app.post(`, etc.
- `@router.get(`, `@router.post(`, etc.
- `Request`, `Response`, `HTTPException`

**Flask (Python)**:

- `@app.route(`
- `@blueprint.route(`
- `request.args`, `request.form`, `request.json`

**Go (net/http, Gin, Echo)**:

- `http.HandleFunc`
- `router.GET(`, `router.POST(`, etc.
- `c.Param(`, `c.Query(`, `c.Bind(`
- `ServeHTTP`

**Rails (Ruby)**:

- `def create`, `def update`, `def destroy`
- `params.require(`, `params.permit(`

## Behavior

When triggered, this skill performs lightweight, non-blocking validation:

1. **Identify the change scope** - Which endpoint, which HTTP method
2. **Check input validation** - User input is validated before use
3. **Check authentication** - Protected endpoints require auth
4. **Check authorization** - Users can only access their own resources
5. **Check rate limiting** - High-risk endpoints have rate limits
6. **Check CSRF protection** - State-changing endpoints are CSRF-protected
7. **Report inline** - Non-blocking feedback

This skill does NOT invoke parallel agents (must remain lightweight for auto-trigger).

## Analysis Checks

### 1. Input Validation

Verify that user input is validated before use:

**Good patterns**:

```python
# Python/FastAPI
from pydantic import BaseModel, validator

class CreateUserRequest(BaseModel):
    email: str
    age: int

    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email')
        return v
```

```javascript
// JavaScript/Express with Joi
const Joi = require("joi");
const schema = Joi.object({
  email: Joi.string().email().required(),
  age: Joi.number().integer().min(0).max(120).required(),
});
const { error, value } = schema.validate(req.body);
```

**Bad patterns**:

```python
# NO validation!
email = request.json['email']
user = User.objects.filter(email=email)  # SQL injection risk
```

**Check**:

- Input schemas defined (Pydantic, Joi, etc.)
- Type validation enforced
- Length/format constraints applied
- Sanitization before database queries

### 2. Authentication Check

Verify that protected endpoints require authentication:

**Good patterns**:

```python
# Python/Django
from rest_framework.permissions import IsAuthenticated

class UserViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
```

```javascript
// JavaScript/Express
const requireAuth = require("./middleware/auth");
app.post("/api/users", requireAuth, createUserHandler);
```

**Bad patterns**:

```javascript
// NO authentication!
app.post("/api/users/:id/delete", async (req, res) => {
  await User.deleteOne({ _id: req.params.id });
  // Anyone can delete any user!
});
```

**Check**:

- Authentication middleware present
- JWT/session validation enforced
- Public endpoints explicitly marked as such

### 3. Authorization (IDOR Protection)

Verify that users can only access their own resources:

**Good patterns**:

```python
# Python - Check ownership
def get_user_profile(request, user_id):
    if request.user.id != user_id and not request.user.is_admin:
        raise PermissionDenied("Cannot access other users' profiles")
    return User.objects.get(id=user_id)
```

```javascript
// JavaScript - Filter by authenticated user
app.get("/api/orders", requireAuth, async (req, res) => {
  const orders = await Order.find({ userId: req.user.id });
  // Only return orders belonging to authenticated user
});
```

**Bad patterns**:

```javascript
// IDOR vulnerability!
app.get("/api/orders/:id", requireAuth, async (req, res) => {
  const order = await Order.findById(req.params.id);
  // No ownership check! Any authenticated user can see any order
});
```

**Check**:

- User ID from auth context, not request parameters
- Resource ownership validated before access
- Admin role checks for privileged operations

### 4. Rate Limiting

Verify that high-risk endpoints have rate limits:

**High-risk endpoints**:

- Login (`/auth/login`)
- Password reset (`/auth/reset-password`)
- Email sending (`/contact`, `/invite`)
- Resource creation (`POST /api/users`, `POST /api/orders`)

**Good patterns**:

```javascript
// Express with express-rate-limit
const rateLimit = require("express-rate-limit");

const loginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 5, // 5 requests per window
  message: "Too many login attempts, please try again later",
});

app.post("/auth/login", loginLimiter, loginHandler);
```

```python
# Django with django-ratelimit
from django_ratelimit.decorators import ratelimit

@ratelimit(key='ip', rate='5/15m', method='POST')
def login(request):
    # ...
```

**Check**:

- Rate limiters configured for sensitive endpoints
- Limits based on IP or user ID
- Appropriate time windows (15min for login, 1h for email)

### 5. CSRF Protection

Verify that state-changing endpoints are CSRF-protected:

**Applies to**:

- All POST, PUT, PATCH, DELETE endpoints
- Endpoints that modify server state
- NOT needed for stateless APIs with token auth

**Good patterns**:

```python
# Django (CSRF enabled by default)
from django.views.decorators.csrf import csrf_protect

@csrf_protect
def transfer_money(request):
    # ...
```

```javascript
// Express with csurf
const csrf = require("csurf");
const csrfProtection = csrf({ cookie: true });

app.post("/transfer", csrfProtection, transferHandler);
```

**Check**:

- CSRF middleware enabled for session-based auth
- Token auth APIs may skip CSRF (stateless)
- State-changing operations protected

### 6. SQL Injection Protection

Verify that database queries use parameterized queries:

**Good patterns**:

```python
# Python - Parameterized query
user = User.objects.filter(email=email).first()  # Django ORM - safe

# Or with raw SQL
cursor.execute("SELECT * FROM users WHERE email = %s", [email])  # Safe
```

```javascript
// JavaScript - Parameterized query
const user = await User.findOne({ email: email }); // Mongoose - safe

// Or with raw SQL
db.query("SELECT * FROM users WHERE email = ?", [email]); // Safe
```

**Bad patterns**:

```python
# String concatenation - VULNERABLE!
query = f"SELECT * FROM users WHERE email = '{email}'"
cursor.execute(query)
```

**Check**:

- ORM used for queries (SQLAlchemy, Django ORM, Sequelize)
- If raw SQL, parameterized queries enforced
- No string concatenation in SQL queries

## Validation Output

When this skill detects issues, it provides inline feedback:

```text
🛡️ API Security Guard Findings:

✅ Input validation: PASS
   - Request schema defined (CreateUserRequest)
   - Email format validated
   - Age bounds checked (0-120)

⚠️  Authorization: WARNING
   - User ID taken from request body instead of auth context
   - Recommendation: Use req.user.id from authentication middleware

❌ Rate limiting: FAIL
   - POST /api/users/create has no rate limit
   - High risk: Resource creation endpoint
   - Add rate limiter: 100 requests per 15 minutes

✅ CSRF protection: PASS
   - csrfProtection middleware applied

✅ SQL injection: PASS
   - Using Sequelize ORM (safe)
```

## Configuration

To disable specific checks, add to `.claude/config/skill_config.yml`:

```yaml
skills:
  api-security-guard:
    enabled: true
    checks:
      input_validation: true
      authentication: true
      authorization: true
      rate_limiting: true
      csrf_protection: true
      sql_injection: true
```

## Related

- `templates/skills/database-migration-guard` - Schema change validation
- `templates/skills/secret-detection-guard` - Credential leak prevention
- `templates/validation-overrides/web-framework-security.yml` - Framework-specific rules
