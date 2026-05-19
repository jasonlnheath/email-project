import Foundation
import Contacts
import GRDB

/// Contact aggregation service - combines contacts from multiple sources
actor ContactAggregationService {
    static let shared = ContactAggregationService()

    private let database = ContactDatabase.shared
    private let contactsService = ContactsService.shared

    private init() {}

    /// Fetch and aggregate contacts from all sources
    func aggregateContacts(accessToken: String) async throws -> [RichContact] {
        // Create database schema if needed
        try await database.createSchema()

        var allContacts: [RichContact] = []

        // 1. Fetch from Gmail
        let gmailContacts = try await fetchGmailContacts(accessToken: accessToken)
        allContacts.append(contentsOf: gmailContacts)

        // 2. Fetch from Apple Contacts
        let appleContacts = try await fetchAppleContacts()
        allContacts.append(contentsOf: appleContacts)

        // 3. Merge contacts by email (priority: Gmail > Apple > Outlook)
        let mergedContacts = try await mergeContacts(allContacts)

        // 4. Store in database
        for contact in mergedContacts {
            try await database.upsertContact(contact)
        }

        return mergedContacts
    }

    // MARK: - Source Fetching

    private func fetchGmailContacts(accessToken: String) async throws -> [RichContact] {
        let contacts = try await contactsService.fetchContacts(accessToken: accessToken)

        return contacts.map { contact in
            RichContact(
                email: contact.email,
                name: contact.name,
                displayName: contact.name,
                phone: contact.phoneNumber,
                photoUrl: contact.photoUrl,
                source: .gmail,
                vipInfo: nil, // Will be populated by user
                attributes: [],
                overallScore: 0.0
            )
        }
    }

    private func fetchAppleContacts() async throws -> [RichContact] {
        let store = CNContactStore()
        var contacts: [RichContact] = []

        let keysToFetch = [
            CNContactGivenNameKey,
            CNContactFamilyNameKey,
            CNContactEmailAddressesKey,
            CNContactPhoneNumbersKey,
            CNContactOrganizationNameKey,
            CNContactJobTitleKey,
            CNContactImageDataAvailableKey,
            CNContactThumbnailImageDataKey,
            CNContactNoteKey
        ]

        let fetchRequest = CNContactFetchRequest(keysToFetch: keysToFetch as [CNKeyDescriptor])

        try store.enumerateContacts(with: fetchRequest) { contact, _ in
            // Extract email
            guard let email = contact.emailAddresses.first?.value as String? else {
                return
            }

            // Build full name
            let name = [contact.givenName, contact.familyName]
                .compactMap { $0 }
                .filter { !$0.isEmpty }
                .joined(separator: " ")

            // Extract phone
            let phone = contact.phoneNumbers.first?.value.stringValue

            // Build RichContact
            let richContact = RichContact(
                email: email,
                name: name.isEmpty ? nil : name,
                displayName: name.isEmpty ? nil : name,
                phone: phone,
                photoUrl: nil, // TODO: Extract photo data
                source: .apple,
                company: contact.organizationName.isEmpty ? nil : contact.organizationName,
                title: contact.jobTitle.isEmpty ? nil : contact.jobTitle,
                notes: contact.note.isEmpty ? nil : contact.note,
                vipInfo: nil,
                attributes: [],
                overallScore: 0.0
            )

            contacts.append(richContact)
        }

        return contacts
    }

    // MARK: - Contact Merging

    private func mergeContacts(_ contacts: [RichContact]) async throws -> [RichContact] {
        var merged: [String: RichContact] = [:]

        for contact in contacts {
            let email = contact.email.lowercased()

            if let existing = merged[email] {
                // Merge with existing contact
                merged[email] = mergeContact(existing, new: contact)
            } else {
                // Add new contact
                merged[email] = contact
            }
        }

        return Array(merged.values)
    }

    private func mergeContact(_ existing: RichContact, new: RichContact) -> RichContact {
        // Priority: Gmail > Apple > Outlook > Manual
        let sourcePriority: [ContactSource: Int] = [
            .gmail: 4,
            .apple: 3,
            .outlook: 2,
            .manual: 1
        ]

        let existingPriority = sourcePriority[existing.source] ?? 0
        let newPriority = sourcePriority[new.source] ?? 0

        // If new source has higher priority, use new data
        if newPriority > existingPriority {
            return new
        }

        // Otherwise, keep existing but fill in missing fields
        return RichContact(
            id: existing.id,
            email: existing.email,
            name: existing.name ?? new.name,
            displayName: existing.displayName ?? new.displayName,
            phone: existing.phone ?? new.phone,
            photoUrl: existing.photoUrl ?? new.photoUrl,
            source: existing.source,
            company: existing.company ?? new.company,
            title: existing.title ?? new.title,
            location: existing.location ?? new.location,
            linkedinUrl: existing.linkedinUrl ?? new.linkedinUrl,
            twitterUrl: existing.twitterUrl ?? new.twitterUrl,
            notes: combineNotes(existing.notes, new.notes),
            vipInfo: existing.vipInfo ?? new.vipInfo,
            attributes: existing.attributes + new.attributes,
            overallScore: max(existing.overallScore, new.overallScore)
        )
    }

    private func combineNotes(_ existing: String?, _ new: String?) -> String? {
        guard let existing = existing, !existing.isEmpty else { return new }
        guard let new = new, !new.isEmpty else { return existing }
        return "\(existing)\n\n---\n\n\(new)"
    }
}
