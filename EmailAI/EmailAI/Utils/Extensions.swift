import Foundation
import SwiftUI

/// Utility for calculating and displaying email priority
struct EmailPriorityCalculator {

    /// Urgent keywords that indicate high priority
    private static let urgentKeywords = [
        "urgent", "asap", "emergency", "immediate", "important",
        "deadline", "expir", "overdue", "action required", "response needed",
        "meeting", "invitation", "confirm", "approve", "review"
    ]

    /// Newsletter/promotion indicators
    private static let newsletterKeywords = [
        "unsubscribe", "newsletter", "promotion", "sale", "discount",
        "offer", "deal", "update", "weekly", "digest"
    ]

    /// Calculate priority for an email based on sender, VIP contacts, and content
    static func calculate(for email: EmailItem, vipContacts: [Contact]) -> EmailPriority {
        // Check if sender is a VIP contact
        if vipContacts.contains(where: { email.sender.contains($0.email) }) {
            return .vipHigh
        }

        // Check subject for urgent keywords
        let lowercaseSubject = email.subject.lowercased()
        for keyword in urgentKeywords where lowercaseSubject.contains(keyword) {
            return .high
        }

        // Check if it's a newsletter/promotion
        let lowercaseBody = email.body.lowercased()
        for keyword in newsletterKeywords where lowercaseBody.contains(keyword) {
            return .low
        }

        // Default to medium
        return .medium
    }

    /// Get the color for a priority level (for left border)
    static func color(for priority: EmailPriority) -> Color {
        switch priority {
        case .vipHigh:
            return Color(red: 1.0, green: 0.84, blue: 0.0) // Gold
        case .high:
            return Color.red
        case .medium:
            return Color.purple
        case .low:
            return Color.gray
        }
    }

    /// Get the background color for a priority level (for badges/indicators)
    static func backgroundColor(for priority: EmailPriority) -> Color {
        switch priority {
        case .vipHigh:
            return Color(red: 1.0, green: 0.92, blue: 0.23) // Light gold
        case .high:
            return Color.red.opacity(0.2)
        case .medium:
            return Color.purple.opacity(0.2)
        case .low:
            return Color.gray.opacity(0.2)
        }
    }
}

extension String {
    /// Rough token count estimate (~4 chars per token for English)
    var estimatedTokenCount: Int {
        max(1, count / 4)
    }

    /// Truncate to max character count with ellipsis
    func truncated(to length: Int) -> String {
        if count <= length { return self }
        return String(prefix(length)) + "..."
    }
}

extension Date {
    /// ISO 8601 string representation
    var iso8601String: String {
        ISO8601DateFormatter().string(from: self)
    }
}

extension Collection where Element: Numeric {
    /// Sum of all elements
    var sum: Element { reduce(0, +) }
}
