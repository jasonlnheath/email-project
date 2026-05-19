import Foundation

/// Priority level for email display and sorting
enum EmailPriority: String, CaseIterable, Codable {
    case vipHigh = "VIP_HIGH"
    case high = "HIGH"
    case medium = "MEDIUM"
    case low = "LOW"

    var displayName: String {
        switch self {
        case .vipHigh: return "VIP"
        case .high: return "High"
        case .medium: return "Medium"
        case .low: return "Low"
        }
    }
}

/// VIP contact information
struct VIPInfo: Codable {
    let name: String
    let relationshipType: String
}

/// Plain Swift data model for Email (used with Core Data entity).
/// The Core Data entity "EmailItem" has matching attributes.
struct EmailItem: Identifiable {
    let id: UUID
    let emailId: String
    let subject: String
    let sender: String
    let date: Date
    let body: String
    let snippet: String
    let gmailUrl: String
    let tier: Int
    let fetchedAt: Date

    // Dashboard feature fields
    var isRead: Bool
    var isStarred: Bool
    var isDeferred: Bool  // Track deferred status
    var priority: EmailPriority
    var summary: String?
    var unsubscribeUrl: String?
    var vipInfo: VIPInfo?
    var isExpanded: Bool  // For expandable UI

    init(
        id: UUID = UUID(),
        emailId: String,
        subject: String,
        sender: String,
        date: Date,
        body: String,
        snippet: String = "",
        gmailUrl: String = "",
        tier: Int = 1,
        fetchedAt: Date = Date(),
        isRead: Bool = false,
        isStarred: Bool = false,
        isDeferred: Bool = false,
        priority: EmailPriority = .medium,
        summary: String? = nil,
        unsubscribeUrl: String? = nil,
        vipInfo: VIPInfo? = nil,
        isExpanded: Bool = false
    ) {
        self.id = id
        self.emailId = emailId
        self.subject = subject
        self.sender = sender
        self.date = date
        self.body = body
        self.snippet = snippet
        self.gmailUrl = gmailUrl
        self.tier = tier
        self.fetchedAt = fetchedAt
        self.isRead = isRead
        self.isStarred = isStarred
        self.isDeferred = isDeferred
        self.priority = priority
        self.summary = summary
        self.unsubscribeUrl = unsubscribeUrl
        self.vipInfo = vipInfo
        self.isExpanded = isExpanded
    }
}
