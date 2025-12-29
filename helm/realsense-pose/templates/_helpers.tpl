{{/*
Expand the name of the chart.
*/}}
{{- define "realsense-pose.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "realsense-pose.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "realsense-pose.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "realsense-pose.labels" -}}
helm.sh/chart: {{ include "realsense-pose.chart" . }}
{{ include "realsense-pose.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "realsense-pose.selectorLabels" -}}
app.kubernetes.io/name: {{ include "realsense-pose.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
API selector labels
*/}}
{{- define "realsense-pose.api.selectorLabels" -}}
{{ include "realsense-pose.selectorLabels" . }}
app.kubernetes.io/component: api
{{- end }}

{{/*
Nginx selector labels
*/}}
{{- define "realsense-pose.nginx.selectorLabels" -}}
{{ include "realsense-pose.selectorLabels" . }}
app.kubernetes.io/component: nginx
{{- end }}

{{/*
MongoDB selector labels
*/}}
{{- define "realsense-pose.mongodb.selectorLabels" -}}
{{ include "realsense-pose.selectorLabels" . }}
app.kubernetes.io/component: mongodb
{{- end }}

{{/*
Redis selector labels
*/}}
{{- define "realsense-pose.redis.selectorLabels" -}}
{{ include "realsense-pose.selectorLabels" . }}
app.kubernetes.io/component: redis
{{- end }}

{{/*
MongoDB connection URI
*/}}
{{- define "realsense-pose.mongoUri" -}}
mongodb://root:$(MONGO_ROOT_PASSWORD)@{{ include "realsense-pose.fullname" . }}-mongodb:27017/admin
{{- end }}

{{/*
Redis URL
*/}}
{{- define "realsense-pose.redisUrl" -}}
redis://{{ include "realsense-pose.fullname" . }}-redis:6379
{{- end }}
