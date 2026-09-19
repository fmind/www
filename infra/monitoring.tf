# https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/monitoring_alert_policy
# Observability: notification channel and Cloud Run error alert policies.

# Notification channel for error alerts.
resource "google_monitoring_notification_channel" "email" {
  display_name = "Médéric Hurier (Email)"
  type         = "email"
  labels = {
    email_address = var.notification_email
  }

  depends_on = [time_sleep.wait_for_apis]
}

# Uptime check: probe the public site's /health endpoint from multiple global
# locations. Catches full outages that produce no 5xx metrics (e.g. the service
# is down, DNS/cert broke, or the domain mapping is misconfigured).
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
      host       = "www.fmind.dev"
    }
  }

  depends_on = [time_sleep.wait_for_apis]
}

# Alert when the /health uptime check fails from more than one location (a single
# flaky probe location alone will not page).
resource "google_monitoring_alert_policy" "uptime_health" {
  display_name = "Uptime Check Failing - ${var.service_name}"
  combiner     = "OR"
  conditions {
    display_name = "/health uptime check failing"
    condition_threshold {
      filter          = "resource.type = \"uptime_url\" AND metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.label.check_id = \"${google_monitoring_uptime_check_config.health.uptime_check_id}\""
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
}

# Alert policy for Cloud Run HTTP 5xx errors.
resource "google_monitoring_alert_policy" "cloudrun_5xx_errors" {
  display_name = "Cloud Run 5xx Errors - ${var.service_name}"
  combiner     = "OR"
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
}

# Alert policy for application-level error logs (severity ERROR or higher).
resource "google_monitoring_alert_policy" "error_logs" {
  display_name = "Cloud Run Error Logs - ${var.service_name}"
  combiner     = "OR"
  conditions {
    display_name = "Log matches error condition"
    condition_matched_log {
      filter = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${var.service_name}\" AND severity>=ERROR"
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
}
