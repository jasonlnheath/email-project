import Foundation

/// Tier 2 email summary data model.
struct SummaryItem: Identifiable {
    let id: UUID
    let emailId: String
    let subject: String
    let sender: String
    let date: Date
    let summaryPurpose: String
    let keyEntities: [String]
    let actionItems: [String]
    let sentiment: String
    let gmailUrl: String

    init(
        id: UUID = UUID(),
        emailId: String,
        subject: String,
        sender: String,
        date: Date,
        summaryPurpose: String,
        keyEntities: [String] = [],
        actionItems: [String] = [],
        sentiment: String = "neutral",
        gmailUrl: String = ""
    ) {
        self.id = id
        self.emailId = emailId
        self.subject = subject
        self.sender = sender
        self.date = date
        self.summaryPurpose = summaryPurpose
        self.keyEntities = keyEntities
        self.actionItems = actionItems
        self.sentiment = sentiment
        self.gmailUrl = gmailUrl
    }
}
