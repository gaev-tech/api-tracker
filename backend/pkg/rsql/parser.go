// Package rsql provides a parser for RSQL (REST Query String Language) expressions.
// Supported operators: ==, !=, <, <=, >, >=, =in=, =out=
// Logical: ; (and), , (or)
// Max expression length: 4096 chars. Max operands in =in=/=out=: 1000.
package rsql

import (
	"errors"
	"fmt"
	"strings"
	"unicode"
)

const (
	maxExprLen   = 4096
	maxInOperands = 1000
)

// NodeType identifies the kind of AST node.
type NodeType int

const (
	NodeAnd NodeType = iota
	NodeOr
	NodeComparison
)

// Node is a node in the RSQL AST.
type Node struct {
	Type     NodeType
	Left     *Node
	Right    *Node
	Field    string
	Operator string
	Values   []string
}

// Parse parses an RSQL expression and returns the root AST node.
func Parse(expr string) (*Node, error) {
	if len(expr) > maxExprLen {
		return nil, fmt.Errorf("rsql: expression exceeds %d characters", maxExprLen)
	}
	p := &parser{input: strings.TrimSpace(expr), pos: 0}
	node, err := p.parseOr()
	if err != nil {
		return nil, err
	}
	if p.pos < len(p.input) {
		return nil, fmt.Errorf("rsql: unexpected input at position %d: %q", p.pos, p.input[p.pos:])
	}
	return node, nil
}

type parser struct {
	input string
	pos   int
}

func (p *parser) peek() byte {
	if p.pos >= len(p.input) {
		return 0
	}
	return p.input[p.pos]
}

func (p *parser) skipSpace() {
	for p.pos < len(p.input) && unicode.IsSpace(rune(p.input[p.pos])) {
		p.pos++
	}
}

// parseOr parses expr (,expr)*
func (p *parser) parseOr() (*Node, error) {
	left, err := p.parseAnd()
	if err != nil {
		return nil, err
	}
	for {
		p.skipSpace()
		if p.peek() != ',' {
			break
		}
		p.pos++ // consume ','
		right, err := p.parseAnd()
		if err != nil {
			return nil, err
		}
		left = &Node{Type: NodeOr, Left: left, Right: right}
	}
	return left, nil
}

// parseAnd parses expr (;expr)*
func (p *parser) parseAnd() (*Node, error) {
	left, err := p.parsePrimary()
	if err != nil {
		return nil, err
	}
	for {
		p.skipSpace()
		if p.peek() != ';' {
			break
		}
		p.pos++ // consume ';'
		right, err := p.parsePrimary()
		if err != nil {
			return nil, err
		}
		left = &Node{Type: NodeAnd, Left: left, Right: right}
	}
	return left, nil
}

// parsePrimary parses a comparison or a parenthesised expression.
func (p *parser) parsePrimary() (*Node, error) {
	p.skipSpace()
	if p.peek() == '(' {
		p.pos++
		node, err := p.parseOr()
		if err != nil {
			return nil, err
		}
		p.skipSpace()
		if p.peek() != ')' {
			return nil, errors.New("rsql: missing closing parenthesis")
		}
		p.pos++
		return node, nil
	}
	return p.parseComparison()
}

func (p *parser) parseComparison() (*Node, error) {
	field := p.parseSelector()
	if field == "" {
		return nil, fmt.Errorf("rsql: expected field name at position %d", p.pos)
	}
	op, err := p.parseOperator()
	if err != nil {
		return nil, err
	}
	values, err := p.parseArguments(op)
	if err != nil {
		return nil, err
	}
	return &Node{Type: NodeComparison, Field: field, Operator: op, Values: values}, nil
}

func (p *parser) parseSelector() string {
	start := p.pos
	for p.pos < len(p.input) {
		ch := rune(p.input[p.pos])
		if unicode.IsLetter(ch) || unicode.IsDigit(ch) || ch == '_' || ch == '.' {
			p.pos++
		} else {
			break
		}
	}
	return p.input[start:p.pos]
}

var operators = []string{"==", "!=", "<=", ">=", "<", ">", "=in=", "=out="}

func (p *parser) parseOperator() (string, error) {
	for _, op := range operators {
		if strings.HasPrefix(p.input[p.pos:], op) {
			p.pos += len(op)
			return op, nil
		}
	}
	return "", fmt.Errorf("rsql: unknown operator at position %d: %q", p.pos, p.input[p.pos:])
}

func (p *parser) parseArguments(op string) ([]string, error) {
	multi := op == "=in=" || op == "=out="
	if multi {
		if p.peek() != '(' {
			return nil, fmt.Errorf("rsql: expected '(' after %s at position %d", op, p.pos)
		}
		p.pos++
		var values []string
		for {
			val, err := p.parseValue()
			if err != nil {
				return nil, err
			}
			values = append(values, val)
			if len(values) > maxInOperands {
				return nil, fmt.Errorf("rsql: too many operands in %s (max %d)", op, maxInOperands)
			}
			p.skipSpace()
			if p.peek() == ')' {
				p.pos++
				break
			}
			if p.peek() != ',' {
				return nil, fmt.Errorf("rsql: expected ',' or ')' in argument list at position %d", p.pos)
			}
			p.pos++
		}
		return values, nil
	}
	val, err := p.parseValue()
	if err != nil {
		return nil, err
	}
	return []string{val}, nil
}

func (p *parser) parseValue() (string, error) {
	p.skipSpace()
	if p.peek() == '"' || p.peek() == '\'' {
		return p.parseQuotedValue()
	}
	start := p.pos
	for p.pos < len(p.input) {
		ch := p.input[p.pos]
		if ch == ',' || ch == ')' || ch == ';' || ch == ' ' {
			break
		}
		p.pos++
	}
	if p.pos == start {
		return "", fmt.Errorf("rsql: empty value at position %d", p.pos)
	}
	return p.input[start:p.pos], nil
}

func (p *parser) parseQuotedValue() (string, error) {
	quote := p.input[p.pos]
	p.pos++
	var sb strings.Builder
	for p.pos < len(p.input) {
		ch := p.input[p.pos]
		p.pos++
		if ch == quote {
			return sb.String(), nil
		}
		if ch == '\\' && p.pos < len(p.input) {
			sb.WriteByte(p.input[p.pos])
			p.pos++
			continue
		}
		sb.WriteByte(ch)
	}
	return "", errors.New("rsql: unterminated quoted value")
}
