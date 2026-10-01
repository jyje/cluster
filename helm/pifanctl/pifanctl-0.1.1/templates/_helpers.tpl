{{- define "pifanctl.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pifanctl.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "pifanctl.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Labels shared by every object. */}}
{{- define "pifanctl.labels" -}}
helm.sh/chart: {{ include "pifanctl.chart" . }}
app.kubernetes.io/name: {{ include "pifanctl.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/* Selector labels of one component: {root: ., component: "agent"} */}}
{{- define "pifanctl.selectorLabels" -}}
app.kubernetes.io/name: {{ include "pifanctl.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "pifanctl.image" -}}
{{- printf "%s:%s" .Values.image.repository (default (printf "v%s" .Chart.AppVersion) .Values.image.tag) -}}
{{- end -}}

{{/*
The Prometheus URL a controller reads from. A group can override it, otherwise
the release-wide prometheus.url applies. Empty means the controller only uses
its own node.
*/}}
{{- define "pifanctl.controllerSource" -}}
{{- if .source -}}{{ .source }}{{- else if .prometheusUrl -}}prometheus{{- else -}}local{{- end -}}
{{- end -}}
