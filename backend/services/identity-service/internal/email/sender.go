package email

import (
	"crypto/tls"
	"fmt"
	"net/smtp"
	"strings"
)

// Sender sends transactional emails via SMTP.
// If no SMTP host is configured it falls back to logging the message to stdout.
type Sender struct {
	host     string
	port     string
	from     string
	password string
}

// NewSender creates a Sender from explicit config values.
// Pass empty host to get a no-op sender that logs to stdout.
func NewSender(host, port, from, password string) *Sender {
	return &Sender{host: host, port: port, from: from, password: password}
}

// SendVerification sends an email verification link to the given address.
// The verificationURL is the full URL the user should visit (e.g. https://app.example.com/verify?token=...).
func (sender *Sender) SendVerification(toEmail, verificationURL string) error {
	subject := "Подтвердите ваш email"
	body := fmt.Sprintf(
		"Добро пожаловать!\r\n\r\nДля подтверждения адреса перейдите по ссылке:\r\n%s\r\n\r\nСсылка действительна 24 часа.",
		verificationURL,
	)
	return sender.send(toEmail, subject, body)
}

func (sender *Sender) send(toEmail, subject, body string) error {
	if sender.host == "" {
		fmt.Printf("[email] to=%s subject=%q\n%s\n", toEmail, subject, body)
		return nil
	}

	msg := buildMessage(sender.from, toEmail, subject, body)
	addr := sender.host + ":" + sender.port

	// Port 465 uses implicit TLS (SMTPS); other ports use STARTTLS via smtp.SendMail.
	if sender.port == "465" {
		return sendSSL(addr, sender.host, sender.from, sender.password, []string{toEmail}, []byte(msg))
	}
	auth := smtp.PlainAuth("", sender.from, sender.password, sender.host)
	return smtp.SendMail(addr, auth, sender.from, []string{toEmail}, []byte(msg))
}

func sendSSL(addr, host, from, password string, to []string, msg []byte) error {
	conn, err := tls.Dial("tcp", addr, &tls.Config{ServerName: host})
	if err != nil {
		return err
	}
	client, err := smtp.NewClient(conn, host)
	if err != nil {
		return err
	}
	defer client.Close()
	auth := smtp.PlainAuth("", from, password, host)
	if err = client.Auth(auth); err != nil {
		return err
	}
	if err = client.Mail(from); err != nil {
		return err
	}
	for _, addr := range to {
		if err = client.Rcpt(addr); err != nil {
			return err
		}
	}
	w, err := client.Data()
	if err != nil {
		return err
	}
	if _, err = w.Write(msg); err != nil {
		return err
	}
	return w.Close()
}

func buildMessage(from, to, subject, body string) string {
	var builder strings.Builder
	builder.WriteString("From: " + from + "\r\n")
	builder.WriteString("To: " + to + "\r\n")
	builder.WriteString("Subject: " + subject + "\r\n")
	builder.WriteString("MIME-Version: 1.0\r\n")
	builder.WriteString("Content-Type: text/plain; charset=UTF-8\r\n")
	builder.WriteString("\r\n")
	builder.WriteString(body)
	return builder.String()
}
