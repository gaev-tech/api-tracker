# Contributing

## Go Code Style

### Naming

**No abbreviations.** Names must be readable without context.

```go
// Bad
func (s *UserStore) FindByID(ctx context.Context, id string) {}
func (h *AuthHandler) Register(c *gin.Context) {}
func (r *RefreshTokenStore) Create(ctx context.Context, uid string) {}

// Good
func (store *UserStore) FindByID(ctx context.Context, userID string) {}
func (handler *AuthHandler) Register(ctx *gin.Context) {}
func (store *RefreshTokenStore) Create(ctx context.Context, userID string) {}
```

This applies to:
- Receiver names (`s`, `h`, `r`, `c` → use the type's role: `store`, `handler`, `service`, etc.)
- Parameters (`ctx` is fine; `id` → `userID`, `uid` → `userID`, `c` in gin handlers → `ctx`)
- Local variables (`u` → `user`, `req` is fine, `err` is fine)

**Exceptions:** `ctx` for `context.Context`, `err` for errors, `ok` for boolean checks — these are universally understood.

### Error handling

Return errors; do not log and swallow. Log only at the top boundary (handler or main).

### Database queries

Use named constants for repeated column lists (e.g. `userColumns`). Do not repeat column lists inline.

### HTTP handlers

Handlers must not contain business logic. Validation and persistence belong in store/service layers.

## Angular Code Style

### Component file structure

Every component must be split into three files inside its own folder:

```
my-component/
  my-component.component.ts
  my-component.component.html
  my-component.component.scss
```

Never use inline templates or styles. The `@Component` decorator must reference external files:

```typescript
@Component({
  selector: 'app-my-component',
  templateUrl: './my-component.component.html',
  styleUrl: './my-component.component.scss',
})
```

### One file — one export

Each TypeScript file must have exactly one exported symbol. Barrel files (`index.ts`) are the exception — they re-export from other files.

### Strict TypeScript

All code uses strict TypeScript. The `any` type is banned — use `unknown` or proper types instead.
