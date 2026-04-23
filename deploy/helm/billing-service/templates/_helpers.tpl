{{/*
Expand the name of the release. Used as the primary resource name.
*/}}
{{- define "service-template.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Chart name.
*/}}
{{- define "service-template.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "service-template.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/name: {{ include "service-template.fullname" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels used by Deployment and Service to match pods.
*/}}
{{- define "service-template.selectorLabels" -}}
app.kubernetes.io/name: {{ include "service-template.fullname" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
