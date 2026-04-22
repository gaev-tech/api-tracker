// Package sentry provides Sentry error tracking integration.
// TODO: I-15 — replace stubs with real getsentry/sentry-go SDK.
package sentry

import "context"

// Init initialises the Sentry SDK with the given DSN.
// TODO: I-15 — call sentry.Init(sentry.ClientOptions{Dsn: dsn}).
func Init(dsn string) error {
	return nil
}

// CaptureError reports an error to Sentry, enriching it with context values
// such as request_id and user_id.
// TODO: I-15 — call sentry.CaptureException(err) with hub from ctx.
func CaptureError(ctx context.Context, err error) {
}
