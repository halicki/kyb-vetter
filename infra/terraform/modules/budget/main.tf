resource "google_monitoring_notification_channel" "email" {
  project      = var.project_id
  display_name = "${var.project_name} budget alerts"
  type         = "email"
  labels       = { email_address = var.alert_email }
}

resource "google_billing_budget" "this" {
  billing_account = var.billing_account
  display_name    = "${var.project_name}-${var.environment}"
  budget_filter {
    projects = ["projects/${var.project_number}"]
  }
  amount {
    specified_amount {
      currency_code = var.currency
      units         = tostring(var.amount)
    }
  }
  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }
  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.email.id]
    disable_default_iam_recipients   = false
  }
}
