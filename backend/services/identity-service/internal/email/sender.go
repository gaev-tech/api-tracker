package email

import (
	"fmt"
	"strconv"

	"gopkg.in/gomail.v2"
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

	port, err := strconv.Atoi(sender.port)
	if err != nil {
		port = 465
	}

	m := gomail.NewMessage()
	m.SetHeader("From", sender.from)
	m.SetHeader("To", toEmail)
	m.SetHeader("Subject", subject)
	m.SetBody("text/plain; charset=UTF-8", body)

	d := gomail.NewDialer(sender.host, port, sender.from, sender.password)
	return d.DialAndSend(m)
}
