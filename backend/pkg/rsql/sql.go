package rsql

import (
	"fmt"
	"strings"
)

// ToSQL translates an RSQL AST node into a SQL WHERE clause fragment.
// allowedFields maps RSQL field names to SQL column expressions (e.g. {"status": "t.status"}).
// Returns the SQL fragment (without WHERE keyword) and positional arguments.
func ToSQL(node *Node, allowedFields map[string]string) (string, []any, error) {
	gen := &sqlGen{fields: allowedFields}
	sql, err := gen.generate(node)
	if err != nil {
		return "", nil, err
	}
	return sql, gen.args, nil
}

type sqlGen struct {
	fields map[string]string
	args   []any
}

func (g *sqlGen) generate(node *Node) (string, error) {
	switch node.Type {
	case NodeAnd:
		left, err := g.generate(node.Left)
		if err != nil {
			return "", err
		}
		right, err := g.generate(node.Right)
		if err != nil {
			return "", err
		}
		return "(" + left + " AND " + right + ")", nil

	case NodeOr:
		left, err := g.generate(node.Left)
		if err != nil {
			return "", err
		}
		right, err := g.generate(node.Right)
		if err != nil {
			return "", err
		}
		return "(" + left + " OR " + right + ")", nil

	case NodeComparison:
		return g.generateComparison(node)

	default:
		return "", fmt.Errorf("rsql: unknown node type %d", node.Type)
	}
}

func (g *sqlGen) generateComparison(node *Node) (string, error) {
	col, ok := g.fields[node.Field]
	if !ok {
		return "", fmt.Errorf("rsql: field %q is not allowed", node.Field)
	}

	switch node.Operator {
	case "==":
		g.args = append(g.args, node.Values[0])
		return fmt.Sprintf("%s = $%d", col, len(g.args)), nil
	case "!=":
		g.args = append(g.args, node.Values[0])
		return fmt.Sprintf("%s != $%d", col, len(g.args)), nil
	case "<":
		g.args = append(g.args, node.Values[0])
		return fmt.Sprintf("%s < $%d", col, len(g.args)), nil
	case "<=":
		g.args = append(g.args, node.Values[0])
		return fmt.Sprintf("%s <= $%d", col, len(g.args)), nil
	case ">":
		g.args = append(g.args, node.Values[0])
		return fmt.Sprintf("%s > $%d", col, len(g.args)), nil
	case ">=":
		g.args = append(g.args, node.Values[0])
		return fmt.Sprintf("%s >= $%d", col, len(g.args)), nil
	case "=in=":
		placeholders := make([]string, len(node.Values))
		for i, v := range node.Values {
			g.args = append(g.args, v)
			placeholders[i] = fmt.Sprintf("$%d", len(g.args))
		}
		return fmt.Sprintf("%s IN (%s)", col, strings.Join(placeholders, ", ")), nil
	case "=out=":
		placeholders := make([]string, len(node.Values))
		for i, v := range node.Values {
			g.args = append(g.args, v)
			placeholders[i] = fmt.Sprintf("$%d", len(g.args))
		}
		return fmt.Sprintf("%s NOT IN (%s)", col, strings.Join(placeholders, ", ")), nil
	default:
		return "", fmt.Errorf("rsql: unsupported operator %q", node.Operator)
	}
}
