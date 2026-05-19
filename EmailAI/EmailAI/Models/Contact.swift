import Foundation

/// Contact from Google People API
struct Contact: Identifiable, Codable {
    let id: UUID
    let email: String
    let name: String?
    let phoneNumber: String?
    let photoUrl: String?
    let lastUpdated: Date

    init(id: UUID = UUID(), email: String, name: String?, phoneNumber: String?, photoUrl: String?, lastUpdated: Date = Date()) {
        self.id = id
        self.email = email
        self.name = name
        self.phoneNumber = phoneNumber
        self.photoUrl = photoUrl
        self.lastUpdated = lastUpdated
    }
}

/// Errors that can occur during contacts operations
enum ContactsError: LocalizedError {
    case invalidToken
    case networkError(Error)
    case parseError(String)

    var errorDescription: String? {
        switch self {
        case .invalidToken:
            return "Invalid or expired access token"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .parseError(let message):
            return "Failed to parse contacts: \(message)"
        }
    }
}
