# https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_alert_policy
# Observability: notification channel, uptime checks, and alert policies.
#
# Cost (Cloud Monitoring pricing, November 2026): uptime checks run from six
# locations every five minutes, about 104k executions a month for both, inside
# the free million per project. Alerting charges start no sooner than September
# 2027 at $0.35 per metric reference a month; uptime-metric policies are exempt,
# so only the 5xx and log-match conditions would then cost about $0.70 a month.

locals {
  # Alert emails link these runbooks; the repository is private, so only the
  # owner can open them.
  runbook_deployment = "https://github.com/fmind/www/blob/main/README.md#deployment"
  runbook_infra      = "https://github.com/fmind/www/blob/main/.agents/skills/infra/SKILL.md"
  uptime_check_ids = [
    google_monitoring_uptime_check_config.health.uptime_check_id,
    google_monitoring_uptime_check_config.apex.uptime_check_id,
  ]
  uptime_check_filter = "resource.type = \"uptime_url\" AND metric.label.check_id = one_of(${join(", ", [for id in local.uptime_check_ids : "\"${id}\""])})"
}

# Notification channel for error alerts.
resource "google_monitoring_notification_channel" "email" {
  display_name = "Médéric Hurier (Email)"
  type         = "email"
  labels = {
    email_address = var.notification_email
  }

  depends_on = [time_sleep.wait_for_apis]
}

# Uptime checks probe /health on both mapped hosts from multiple global
# locations. They catch full outages that produce no 5xx metrics (the service is
# down, DNS or a managed certificate broke, or a domain mapping is
# misconfigured) and, with validate_ssl, report each certificate's remaining days.
resource "google_monitoring_uptime_check_config" "health" {
  display_name = "Uptime - ${var.service_name} /health"
  timeout      = "10s"
  period       = "300s" # every 5 minutes

  http_check {
    path         = "/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = "www.${var.apex_domain}"
    }
  }

  depends_on = [time_sleep.wait_for_apis]
}

# The apex mapping has its own managed certificate and answers every GET,
# /health included, with a 301 to www. Public Cloud Monitoring uptime checks
# follow HTTP redirects, validating TLS on the initial apex handshake and
# evaluating the final www /health 200 response (accepting 301 alone fails every
# probe because the followed hop answers 200).
resource "google_monitoring_uptime_check_config" "apex" {
  display_name = "Uptime - ${var.service_name} apex redirect"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.apex_domain
    }
  }

  depends_on = [time_sleep.wait_for_apis]
}

# Alert when a host's uptime check fails from more than one location (a single
# flaky probe location alone will not page). Grouping by host alerts each
# mapping separately.
resource "google_monitoring_alert_policy" "uptime_health" {
  display_name = "Uptime Check Failing - ${var.service_name}"
  combiner     = "OR"
  severity     = "CRITICAL"
  conditions {
    display_name = "/health uptime check failing"
    condition_threshold {
      filter          = "${local.uptime_check_filter} AND metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "60s"
      trigger {
        count = 1
      }
      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.email.name
  ]

  alert_strategy {
    auto_close = "172800s"
  }

  documentation {
    mime_type = "text/markdown"
    subject   = "Uptime check failing for ${var.apex_domain} or www.${var.apex_domain}"
    content   = <<-EOT
      Several probe locations get no healthy /health answer: 200 on www, or a 301 to www on the apex. Visitors to that host see an outage.

      1. Run `curl -sSI https://www.${var.apex_domain}/health` and `curl -sSI https://${var.apex_domain}/health` to see which host fails and how (status or TLS).
      2. Run `gcloud run services describe ${var.service_name} --region=${var.region} --project=${var.project_id}` for readiness and traffic, then read the serving revision's error logs.
      3. Run `gcloud beta run domain-mappings describe --domain=<host> --region=${var.region} --project=${var.project_id}` for mapping and certificate status; DNS is hosted outside Google Cloud.
      4. Roll back a bad revision with `mise run deploy <digest-ref> <commit-sha>` (README, Deployment).
    EOT
    links {
      display_name = "README: Deployment"
      url          = local.runbook_deployment
    }
    links {
      display_name = "Infra skill"
      url          = local.runbook_infra
    }
  }
}

# Google renews managed certificates about a month before they expire, so fewer
# than 21 days left means renewal is stuck, usually because the DNS records at
# the external host drifted. Expiry would otherwise surface only as an outage.
# Note: while the apex 301 redirects to www, Cloud Monitoring records
# time_until_ssl_cert_expires from the final hop (www); an expired apex
# certificate still fails validate_ssl in uptime_health immediately.
resource "google_monitoring_alert_policy" "tls_expiry" {
  display_name = "TLS Certificate Expiring - ${var.service_name}"
  combiner     = "OR"
  severity     = "WARNING"
  conditions {
    display_name = "Managed certificate expires in under 21 days"
    condition_threshold {
      filter          = "${local.uptime_check_filter} AND metric.type = \"monitoring.googleapis.com/uptime_check/time_until_ssl_cert_expires\""
      comparison      = "COMPARISON_LT"
      threshold_value = 21
      duration        = "600s"
      trigger {
        count = 1
      }
      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_MIN"
        group_by_fields      = ["resource.label.host"]
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.email.name
  ]

  alert_strategy {
    auto_close = "172800s"
  }

  documentation {
    mime_type = "text/markdown"
    subject   = "Managed certificate for ${var.apex_domain} or www.${var.apex_domain} is not renewing"
    content   = <<-EOT
      A host's Google-managed certificate has fewer than 21 days left, so renewal has stalled. When it expires, that host fails TLS.

      1. Run `gcloud beta run domain-mappings describe --domain=<host> --region=${var.region} --project=${var.project_id}` and read the certificate and readiness conditions.
      2. Compare the records the mapping expects (`status.resourceRecords`) with those at the external DNS host, and fix any drift there.
      3. Confirm the renewal with `echo | openssl s_client -connect <host>:443 -servername <host> 2>/dev/null | openssl x509 -noout -enddate`.
    EOT
    links {
      display_name = "Infra skill"
      url          = local.runbook_infra
    }
  }
}

# Alert policy for Cloud Run HTTP 5xx errors.
resource "google_monitoring_alert_policy" "cloudrun_5xx_errors" {
  display_name = "Cloud Run 5xx Errors - ${var.service_name}"
  combiner     = "OR"
  severity     = "ERROR"
  conditions {
    display_name = "HTTP 5xx Error Rate > 0"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"${var.service_name}\" AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.email.name
  ]

  alert_strategy {
    auto_close = "172800s" # 2 days
  }

  documentation {
    mime_type = "text/markdown"
    subject   = "${var.service_name} answered 5xx responses"
    content   = <<-EOT
      The service answered 5xx responses for at least a minute.

      1. Read the error logs: `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="${var.service_name}" AND severity>=ERROR' --project=${var.project_id} --freshness=1h --limit=20`.
      2. Run `gcloud run services describe ${var.service_name} --region=${var.region} --project=${var.project_id}` to see which revision serves traffic.
      3. If a new revision causes the errors, roll back with `mise run deploy <digest-ref> <commit-sha>` (README, Deployment).
    EOT
    links {
      display_name = "README: Deployment"
      url          = local.runbook_deployment
    }
  }
}

# Alert policy for application error logs (severity ERROR or higher) and
# capacity aborts. The application never answers 429, so a 429 is Cloud Run
# rejecting a request with "no available instance", which it logs at WARNING.
resource "google_monitoring_alert_policy" "error_logs" {
  display_name = "Cloud Run Error Logs - ${var.service_name}"
  combiner     = "OR"
  severity     = "ERROR"
  conditions {
    display_name = "Error log or capacity abort (429)"
    condition_matched_log {
      filter = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${var.service_name}\" AND (severity>=ERROR OR httpRequest.status=429)"
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.email.name
  ]

  alert_strategy {
    notification_rate_limit {
      period = "300s" # once per 5 minutes to prevent spam
    }
    auto_close = "172800s"
  }

  documentation {
    mime_type = "text/markdown"
    subject   = "${var.service_name} logged an error or a capacity abort"
    content   = <<-EOT
      The service logged an ERROR, or Cloud Run aborted a request with 429 because no instance was available.

      1. Read the matching entries: `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="${var.service_name}" AND (severity>=ERROR OR httpRequest.status=429)' --project=${var.project_id} --freshness=1h --limit=20`.
      2. For a 429, check instance count and latency in the Cloud Run metrics. Repeated aborts at the five-instance cap need an owner decision on capacity, never a silent raise.
      3. If a new revision introduced the error, roll back with `mise run deploy <digest-ref> <commit-sha>` (README, Deployment).
    EOT
    links {
      display_name = "README: Deployment"
      url          = local.runbook_deployment
    }
  }
}
