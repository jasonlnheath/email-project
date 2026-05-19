import Foundation

/// Chat message data model.
struct ChatMessageItem: Identifiable {
    let id: UUID
    let role: String   // "user", "assistant", "system"
    let content: String
    let timestamp: Date

    init(
        id: UUID = UUID(),
        role: String,
        content: String,
        timestamp: Date = Date()
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.timestamp = timestamp
    }
}
