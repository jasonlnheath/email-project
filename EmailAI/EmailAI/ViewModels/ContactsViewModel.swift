import Foundation
import SwiftUI

/// ViewModel for managing contacts list
@MainActor
class ContactsViewModel: ObservableObject {
    @Published var contacts: [Contact] = []
    @Published var isSyncing = false
    @Published var errorMessage: String?
    @Published var lastSync: Date?

    private let contactsService = ContactsService.shared

    /// Sync contacts from Google People API
    func syncContacts() async {
        isSyncing = true
        errorMessage = nil

        do {
            let token = try await OAuthService.shared.getCurrentAccessToken()
            let fetchedContacts = try await contactsService.fetchContacts(accessToken: token)
            contacts = fetchedContacts
            lastSync = Date()
        } catch let error as ContactsError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }

        isSyncing = false
    }

    /// Get contact for a specific email address
    func getContact(for email: String) -> Contact? {
        return contacts.first { $0.email == email }
    }

    /// Search contacts by name or email
    func searchContacts(query: String) -> [Contact] {
        guard !query.isEmpty else {
            return contacts
        }

        return contacts.filter { contact in
            (contact.name?.localizedCaseInsensitiveContains(query) ?? false) ||
            contact.email.localizedCaseInsensitiveContains(query)
        }
    }
}
