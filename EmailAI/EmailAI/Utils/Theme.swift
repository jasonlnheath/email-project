import SwiftUI

/// Theme options for the app
enum AppTheme: String, CaseIterable {
    case light
    case dark
    case system

    var displayName: String {
        switch self {
        case .light: return "Light"
        case .dark: return "Dark"
        case .system: return "System"
        }
    }

    @AppStorage("selectedTheme") static var current: AppTheme = .system
}

/// Theme colors for the app
struct ThemeColors {
    /// Background color based on theme
    static func background(for theme: AppTheme) -> Color {
        switch theme {
        case .light, .system:
            return Color(.systemBackground)
        case .dark:
            return Color(.systemBackground)
        }
    }

    /// Secondary background color (for cards, sections)
    static func secondaryBackground(for theme: AppTheme) -> Color {
        switch theme {
        case .light:
            return Color(.secondarySystemBackground)
        case .dark:
            return Color(red: 0.11, green: 0.11, blue: 0.12)
        case .system:
            return Color(.secondarySystemBackground)
        }
    }

    /// Tertiary background color
    static func tertiaryBackground(for theme: AppTheme) -> Color {
        Color(.tertiarySystemBackground)
    }

    /// Primary text color
    static func text(for theme: AppTheme) -> Color {
        Color(.label)
    }

    /// Secondary text color
    static func secondaryText(for theme: AppTheme) -> Color {
        Color(.secondaryLabel)
    }

    /// Accent color
    static func accent(for theme: AppTheme) -> Color {
        .accentColor
    }

    /// Border color
    static func border(for theme: AppTheme) -> Color {
        Color(.separator)
    }

    /// Priority color for email cards
    static func priorityColor(for priority: EmailPriority) -> Color {
        switch priority {
        case .vipHigh:
            return Color(red: 0.85, green: 0.65, blue: 0.13) // Gold
        case .high:
            return Color(red: 0.8, green: 0.2, blue: 0.2) // Red
        case .medium:
            return Color(red: 0.4, green: 0.3, blue: 0.7) // Purple
        case .low:
            return Color(.gray)
        }
    }

    /// Card background color based on priority
    static func cardBackground(for priority: EmailPriority, theme: AppTheme) -> Color {
        switch priority {
        case .vipHigh:
            return theme == .dark ?
                Color(red: 0.2, green: 0.15, blue: 0.05) :
                Color(red: 1.0, green: 0.98, blue: 0.9)
        case .high:
            return theme == .dark ?
                Color(red: 0.2, green: 0.05, blue: 0.05) :
                Color(red: 1.0, green: 0.95, blue: 0.95)
        case .medium:
            return theme == .dark ?
                Color(red: 0.12, green: 0.08, blue: 0.18) :
                Color(red: 0.98, green: 0.96, blue: 1.0)
        case .low:
            return secondaryBackground(for: theme)
        }
    }

    /// Returns the current color scheme based on theme
    static func colorScheme(for theme: AppTheme) -> ColorScheme? {
        switch theme {
        case .light:
            return .light
        case .dark:
            return .dark
        case .system:
            return nil
        }
    }
}
