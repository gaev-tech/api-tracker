package domain

const (
	PlanFree       = "free"
	PlanPro        = "pro"
	PlanTeam       = "team"
	PlanEnterprise = "enterprise"
)

const Unlimited = -1

type PlanLimits struct {
	TasksTotal              int
	ProjectsOwned           int
	TeamsOwned              int
	AutomationsPerProject   int
	MembersPerProjectOrTeam int
	ManagedUsers            int
}

var Plans = map[string]PlanLimits{
	PlanFree: {
		TasksTotal:              200,
		ProjectsOwned:           3,
		TeamsOwned:              3,
		AutomationsPerProject:   3,
		MembersPerProjectOrTeam: 10,
		ManagedUsers:            3,
	},
	PlanPro: {
		TasksTotal:              Unlimited,
		ProjectsOwned:           20,
		TeamsOwned:              20,
		AutomationsPerProject:   20,
		MembersPerProjectOrTeam: 50,
		ManagedUsers:            20,
	},
	PlanTeam: {
		TasksTotal:              Unlimited,
		ProjectsOwned:           Unlimited,
		TeamsOwned:              Unlimited,
		AutomationsPerProject:   Unlimited,
		MembersPerProjectOrTeam: 100,
		ManagedUsers:            100,
	},
	PlanEnterprise: {
		TasksTotal:              Unlimited,
		ProjectsOwned:           Unlimited,
		TeamsOwned:              Unlimited,
		AutomationsPerProject:   Unlimited,
		MembersPerProjectOrTeam: 100, // base; +1 per enterprise slot
		ManagedUsers:            Unlimited,
	},
}

const (
	EntityTypeTask       = "task"
	EntityTypeProject    = "project"
	EntityTypeTeam       = "team"
	EntityTypeAutomation = "automation"
	EntityTypeMember     = "member"
	EntityTypeManagedUser = "managed_user"
)

// LimitForEntity returns the limit for a given plan and entity type.
// Returns Unlimited (-1) if the entity type has no limit on this plan.
func LimitForEntity(plan string, entityType string, enterpriseSlots int) int {
	p, ok := Plans[plan]
	if !ok {
		return 0
	}
	switch entityType {
	case EntityTypeTask:
		return p.TasksTotal
	case EntityTypeProject:
		return p.ProjectsOwned
	case EntityTypeTeam:
		return p.TeamsOwned
	case EntityTypeAutomation:
		return p.AutomationsPerProject
	case EntityTypeMember:
		limit := p.MembersPerProjectOrTeam
		if plan == PlanEnterprise && limit != Unlimited {
			limit += enterpriseSlots
		}
		return limit
	case EntityTypeManagedUser:
		return p.ManagedUsers
	default:
		return 0
	}
}
