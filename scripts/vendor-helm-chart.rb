#!/usr/bin/env ruby
# frozen_string_literal: true

require 'json'
require 'open3'
require 'pathname'
require 'tmpdir'
require 'yaml'

ROOT = Pathname.new(File.expand_path('..', __dir__))
RESOURCE_KEYS = %w[extraResources extraObjects extraDeploy customResources additionalResources].freeze
EXTRA_RESOURCES = <<~HELM
  {{- range .Values.extraResources }}
  ---
  {{- if typeIs "string" . }}
    {{- tpl . $ }}
  {{- else }}
    {{- tpl (toYaml .) $ }}
  {{- end }}
  {{- end }}
HELM

def yaml(path)
  YAML.safe_load_file(path, aliases: true) || {}
end

def helm(*args, values: nil)
  output, _, status = Open3.capture3('helm', *args.map(&:to_s), stdin_data: values ? JSON.generate(values) : '')
  raise "helm #{args.first} failed (exit #{status.exitstatus})" unless status.success?

  output
end

def injection_keys(chart)
  values = yaml(chart.join('values.yaml'))
  templates = chart.glob('templates/**/*').select(&:file?).map(&:read)
  RESOURCE_KEYS.select do |key|
    values.key?(key) && templates.any? { |template| template.match?(/\.Values\.#{key}\b/) }
  end
end

def patch_injection(chart)
  keys = injection_keys(chart)
  return unless keys.empty?

  template = chart.join('templates/extra-resources.yaml')
  raise 'Chart already contains an unrecognized extra-resources template' if template.exist?

  template.write(EXTRA_RESOURCES)
  values = chart.join('values.yaml')
  values.open('a') { |out| out.write("\nextraResources: []\n") } unless yaml(values).key?('extraResources')
  schema_file = chart.join('values.schema.json')
  return unless schema_file.file?

  schema = JSON.parse(schema_file.read)
  schema['properties'] ||= {}
  schema['properties']['extraResources'] ||= {
    'type' => 'array', 'items' => { 'type' => %w[object string] }
  }
  schema_file.write(JSON.pretty_generate(schema) + "\n")
end

def render_args(chart, app)
  helm_settings = app.fetch('spec').fetch('source').fetch('helm', {})
  release = helm_settings.fetch('releaseName', app.fetch('metadata').fetch('name'))
  namespace = app.fetch('spec').fetch('destination').fetch('namespace')
  ['template', release, chart, '--namespace', namespace, '--include-crds', '-f', '-']
end

def validate(chart, name, version, app, app_values)
  metadata = yaml(chart.join('Chart.yaml'))
  unless metadata.values_at('name', 'version') == [name, version]
    raise 'Chart.yaml name or version does not match the catalog'
  end

  keys = injection_keys(chart)
  raise 'Chart has no resource injection support' if keys.empty?
  missing = (app_values.keys & RESOURCE_KEYS) - keys
  raise "Existing Application resource injection needs review: #{missing.join(', ')}" unless missing.empty?

  helm('lint', chart)
  template = render_args(chart, app)
  rendered = helm(*template, values: app_values)
  return rendered unless keys.include?('extraResources')

  namespace = app.fetch('spec').fetch('destination').fetch('namespace')
  probes = [
    { 'apiVersion' => 'v1', 'kind' => 'ConfigMap', 'metadata' => { 'name' => 'vendor-object-probe' } },
    "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: vendor-string-probe-{{ .Release.Namespace }}\n"
  ]
  probe_render = helm(*template, values: app_values.merge('extraResources' => probes))
  unless probe_render.include?('name: vendor-object-probe') &&
         probe_render.include?("name: vendor-string-probe-#{namespace}")
    raise 'Object or templated string resource injection did not render'
  end
  rendered
end

def report_values(before, after, overrides, prefix = '')
  (before.keys | after.keys).sort.each do |key|
    path = "#{prefix}/#{key}"
    if !after.key?(key)
      puts "Removed value #{path}#{' (Application override)' if overrides.key?(key)}"
    elsif !before.key?(key)
      puts "Added value #{path}"
    elsif before[key].is_a?(Hash) && after[key].is_a?(Hash)
      nested = overrides[key]
      report_values(before[key], after[key], nested.is_a?(Hash) ? nested : {}, path)
    elsif before[key] != after[key]
      puts "Changed default #{path}#{' (Application override)' if overrides.key?(key)}"
    end
  end
end

def crds(rendered)
  rendered.split(/^---[ \t]*$/).grep(/^kind:[ \t]+CustomResourceDefinition[ \t]*$/)
end

def vendor(target, name, source, version, app, values)
  pull = if source.start_with?('oci://')
           [source]
         elsif source.start_with?('https://')
           [name, '--repo', source]
         else
           raise 'Chart source must use OCI or HTTPS'
         end
  Dir.mktmpdir('.helm-vendor-', target.dirname) do |stage|
    helm('pull', *pull, '--version', version, '--untar', '--untardir', stage)
    downloaded = Pathname.new(stage).join(name)
    patch_injection(downloaded)
    rendered = validate(downloaded, name, version, app, values)
    downloaded.rename(target)
    rendered
  end
end

begin
  check = ARGV == ['--check']
  raise 'Usage: ruby scripts/vendor-helm-chart.rb [--check]' unless ARGV.empty? || check

  config = JSON.parse(ROOT.join('helm-sources/error-pages.json').read)
  group, name, source, version, application = config.values_at('group', 'chart', 'source', 'version', 'application')
  unless [group, name].all? { |part| part.match?(/\A[a-z0-9][a-z0-9.-]*\z/) } &&
         version.match?(/\Av?\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.+-]+)?\z/) &&
         application.match?(%r{\Aclusters/[a-z0-9-]+/apps/[a-z0-9-]+\.yaml\z})
    raise 'Invalid chart catalog entry'
  end

  app = yaml(ROOT.join(application))
  app_source = app.fetch('spec').fetch('source')
  app_helm = app_source.fetch('helm', {})
  unless (app_helm.keys - %w[releaseName valuesObject]).empty?
    raise 'Application Helm overrides require manual review'
  end
  app_values = app_helm.fetch('valuesObject', {})
  deployed = app_source.fetch('path')
  unless app_source['repoURL'] == 'https://github.com/jyje/cluster' &&
         deployed.match?(%r{\Ahelm/#{Regexp.escape(group)}/#{Regexp.escape(name)}-v?\d[^/]*\z})
    raise 'Application does not reference a local chart from the catalog'
  end

  previous = ROOT.join(deployed)
  old_crds = crds(helm(*render_args(previous, app), values: app_values))
  target = ROOT.join('helm', group, "#{name}-#{version}")
  rendered = if target.exist? || check
               validate(target, name, version, app, app_values)
             else
               vendor(target, name, source, version, app, app_values)
             end

  puts "Validated #{target.relative_path_from(ROOT)} with #{application} values"
  old_values = yaml(previous.join('values.yaml'))
  new_values = yaml(target.join('values.yaml'))
  if old_values == new_values
    puts 'Chart value defaults are unchanged.'
  else
    report_values(old_values, new_values, app_values)
  end
  old_dependencies = yaml(previous.join('Chart.yaml')).fetch('dependencies', [])
  new_dependencies = yaml(target.join('Chart.yaml')).fetch('dependencies', [])
  puts 'Chart dependencies changed. Review the Chart.yaml diff.' unless old_dependencies == new_dependencies
  puts 'Rendered CRDs changed. Review the CRD diff.' unless old_crds == crds(rendered)
rescue StandardError => e
  warn(e.is_a?(Psych::Exception) || e.is_a?(JSON::ParserError) ? 'Could not parse chart or Application configuration' : e.message)
  exit 1
end
