import SwiftUI

/// Sort options for emails
enum SortOption: String, CaseIterable {
    case priority = "Priority"
    case date = "Date"
    case sender = "Sender"
    case subject = "Subject"

    var displayName: String {
        rawValue
    }
}

/// Filter options for emails
struct EmailFilter {
    var showUnreadOnly: Bool = false
    var showVIPOnly: Bool = false
    var showStarredOnly: Bool = false
    var priorityFilter: EmailPriority? = nil
    var senderFilter: String? = nil
}

@MainActor
class EmailListViewModel: ObservableObject {
    @Published var emails: [EmailItem] = []
    @Published var summaries: [SummaryItem] = []
    @Published var isFetching = false
    @Published var errorMessage: String?
    @Published var isSignedIn = false
    @Published var vipContacts: [Contact] = []

    @Published var currentSortOption: SortOption = .priority
    @Published var currentFilter: EmailFilter = EmailFilter()

    // Search properties
    @Published var searchQuery: String = ""
    @Published var searchScope: SearchScope = .all
    @Published var searchResults: [EmailSearchResult] = []
    @Published var isSearching: Bool = false

    private let gmailService = GmailService()
    private let contactsService = ContactsService.shared
    private let gmailActionsService = GmailActionsService()
    private let searchService = EmailSearchService()

    init() {
        Task {
            isSignedIn = await OAuthService.shared.isSignedIn
        }
    }

    func fetchEmails() {
        isFetching = true
        errorMessage = nil

        Task { [weak self] in
            guard let self = self else { return }

            do {
                // Get OAuth token
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()

                // Fetch VIP contacts for priority calculation
                let contacts = try await self.contactsService.fetchContacts(accessToken: accessToken)
                self.vipContacts = contacts

                // Fetch emails from Gmail
                let gmailMessages = try await self.gmailService.fetchEmails(accessToken: accessToken)

                // Convert to EmailItem models with new fields
                let dateFormatter = ISO8601DateFormatter()
                let items = gmailMessages.map { message -> EmailItem in
                    let emailItem = EmailItem(
                        emailId: message.id,
                        subject: message.subject,
                        sender: message.sender,
                        date: dateFormatter.date(from: message.date) ?? Date(),
                        body: message.body,
                        snippet: message.snippet,
                        gmailUrl: message.gmailUrl,
                        isRead: !message.isUnread,
                        isStarred: message.isStarred,
                        isDeferred: message.isDeferred,
                        priority: .medium,  // Will be calculated below
                        unsubscribeUrl: message.unsubscribeUrl
                    )

                    // Calculate priority based on VIP contacts and content
                    let priority = EmailPriorityCalculator.calculate(for: emailItem, vipContacts: contacts)
                    var updatedItem = emailItem
                    updatedItem.priority = priority

                    // Set VIP info if applicable
                    if let vip = contacts.first(where: { emailItem.sender.contains($0.email) }) {
                        updatedItem.vipInfo = VIPInfo(name: vip.name ?? "Unknown", relationshipType: "VIP")
                    }

                    return updatedItem
                }

                await MainActor.run {
                    self.emails = items
                    self.isFetching = false
                    self.isSignedIn = true
                }
            } catch {
                await MainActor.run {
                    self.isFetching = false

                    // If error is about missing API key, user needs to sign in
                    if case LLMError.missingAPIKey = error {
                        self.errorMessage = "Please sign in with Google to fetch emails"
                    } else {
                        self.errorMessage = error.localizedDescription
                    }
                }
            }
        }
    }

    func loadSampleData() {
        emails = (0..<20).map { i in
            EmailItem(
                emailId: "sample_\(i)",
                subject: "Sample Email \(i + 1)",
                sender: "sender\(i)@example.com",
                date: Date().addingTimeInterval(Double(-i * 3600)),
                body: "This is the body of sample email \(i + 1). It contains some content about various topics like budgets, meetings, and project updates.",
                snippet: "This is the body of sample email \(i + 1)..."
            )
        }
    }

    func signOut() {
        Task {
            do {
                try await OAuthService.shared.signOut()
                await MainActor.run {
                    self.emails = []
                    self.summaries = []
                    self.isSignedIn = false
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = error.localizedDescription
                }
            }
        }
    }

    // MARK: - Email Actions

    func toggleRead(for email: EmailItem) {
        Task {
            do {
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                let newReadState = !email.isRead
                if newReadState {
                    try await gmailActionsService.markAsRead(emailId: email.emailId, accessToken: accessToken)
                } else {
                    try await gmailActionsService.markAsUnread(emailId: email.emailId, accessToken: accessToken)
                }

                await MainActor.run {
                    self.emails = self.emails.map { email in
                        if email.emailId == email.emailId {
                            var updated = email
                            updated.isRead = newReadState
                            return updated
                        }
                        return email
                    }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to update read status: \(error.localizedDescription)"
                }
            }
        }
    }

    func toggleStar(for email: EmailItem) {
        Task {
            do {
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                let newStarState = !email.isStarred
                try await gmailActionsService.toggleStar(emailId: email.emailId, isStarred: newStarState, accessToken: accessToken)

                await MainActor.run {
                    self.emails = self.emails.map { email in
                        if email.emailId == email.emailId {
                            var updated = email
                            updated.isStarred = newStarState
                            return updated
                        }
                        return email
                    }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to update star status: \(error.localizedDescription)"
                }
            }
        }
    }

    func deleteEmail(_ email: EmailItem) {
        Task {
            do {
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                try await gmailActionsService.deleteEmail(emailId: email.emailId, accessToken: accessToken)

                await MainActor.run {
                    self.emails.removeAll { $0.emailId == email.emailId }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to delete email: \(error.localizedDescription)"
                }
            }
        }
    }

    func deferEmail(_ email: EmailItem) {
        Task {
            do {
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                try await gmailActionsService.deferEmail(emailId: email.emailId, accessToken: accessToken)

                await MainActor.run {
                    // Remove the email from the displayed list since it's now archived
                    self.emails.removeAll { $0.emailId == email.emailId }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to defer email: \(error.localizedDescription)"
                }
            }
        }
    }

    func unsubscribe(from email: EmailItem) {
        Task {
            do {
                guard let unsubscribeUrl = email.unsubscribeUrl else {
                    await MainActor.run {
                        self.errorMessage = "No unsubscribe URL available for this email"
                    }
                    return
                }

                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                try await gmailActionsService.unsubscribe(emailId: email.emailId, unsubscribeUrl: unsubscribeUrl, accessToken: accessToken)

                await MainActor.run {
                    self.emails.removeAll { $0.emailId == email.emailId }
                    self.errorMessage = "Unsubscribed successfully"
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to unsubscribe: \(error.localizedDescription)"
                }
            }
        }
    }

    func summarizeEmail(_ email: EmailItem) {
        Task {
            do {
                let llm = LLMProviderFactory.shared.getSelectedProvider()
                let result = try await llm.summarizeEmail(
                    subject: email.subject,
                    sender: email.sender,
                    body: String(email.body.prefix(3000))
                )

                await MainActor.run {
                    self.emails = self.emails.map { email in
                        if email.emailId == email.emailId {
                            var updated = email
                            updated.summary = result.summaryPurpose
                            return updated
                        }
                        return email
                    }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to summarize: \(error.localizedDescription)"
                }
            }
        }
    }

    // MARK: - Sorting and Filtering

    /// Returns filtered and sorted emails based on current settings
    var filteredAndSortedEmails: [EmailItem] {
        var result = emails

        // Apply filters
        if currentFilter.showUnreadOnly {
            result = result.filter { !$0.isRead }
        }
        if currentFilter.showVIPOnly {
            result = result.filter { $0.priority == .vipHigh }
        }
        if currentFilter.showStarredOnly {
            result = result.filter { $0.isStarred }
        }
        if let priorityFilter = currentFilter.priorityFilter {
            result = result.filter { $0.priority == priorityFilter }
        }
        if let senderFilter = currentFilter.senderFilter, !senderFilter.isEmpty {
            result = result.filter { $0.sender.localizedCaseInsensitiveContains(senderFilter) }
        }

        // Apply sorting
        return sortEmails(result, by: currentSortOption)
    }

    /// Sort emails by the specified option
    func sortEmails(_ emails: [EmailItem], by option: SortOption) -> [EmailItem] {
        switch option {
        case .priority:
            // Sort by priority (VIP_HIGH > HIGH > MEDIUM > LOW)
            return emails.sorted { lhs, rhs in
                let lhsOrder = priorityOrder(lhs.priority)
                let rhsOrder = priorityOrder(rhs.priority)
                if lhsOrder != rhsOrder {
                    return lhsOrder < rhsOrder
                }
                // Secondary sort by date (newest first)
                return lhs.date > rhs.date
            }
        case .date:
            // Sort by date (newest first)
            return emails.sorted { $0.date > $1.date }
        case .sender:
            // Sort by sender alphabetically
            return emails.sorted { $0.sender.localizedCaseInsensitiveCompare($1.sender) == .orderedAscending }
        case .subject:
            // Sort by subject alphabetically
            return emails.sorted { $0.subject.localizedCaseInsensitiveCompare($1.subject) == .orderedAscending }
        }
    }

    /// Returns the numeric order for priority (lower = higher priority)
    private func priorityOrder(_ priority: EmailPriority) -> Int {
        switch priority {
        case .vipHigh: return 0
        case .high: return 1
        case .medium: return 2
        case .low: return 3
        }
    }

    /// Update the sort option and re-sort
    func updateSortOption(_ option: SortOption) {
        currentSortOption = option
    }

    /// Update the filter and re-filter
    func updateFilter(_ filter: EmailFilter) {
        currentFilter = filter
    }

    /// Clear all filters
    func clearFilters() {
        currentFilter = EmailFilter()
    }

    /// Reset to default sort and filter
    func resetSortAndFilter() {
        currentSortOption = .priority
        currentFilter = EmailFilter()
    }

    // MARK: - Search

    /// Returns displayed emails (filtered/sorted or search results)
    var displayedEmails: [EmailItem] {
        if isSearching && !searchQuery.isEmpty {
            // Return search results
            return searchResults.map { $0.email }
        } else {
            // Return filtered and sorted emails
            return filteredAndSortedEmails
        }
    }

    /// Perform email search
    func performSearch() async {
        guard !searchQuery.trimmingCharacters(in: .whitespaces).isEmpty else {
            isSearching = false
            searchResults = []
            return
        }

        isSearching = true

        do {
            // Index emails if not already indexed
            if await searchService.indexedEmailsCount == 0 {
                await searchService.indexEmails(emails)
            }

            // Perform search
            let results = try await searchService.search(
                query: searchQuery,
                scope: searchScope,
                limit: 50
            )

            searchResults = results
        } catch {
            errorMessage = "Search failed: \(error.localizedDescription)"
            searchResults = []
        }

        isSearching = false
    }

    /// Clear search and return to normal view
    func clearSearch() {
        searchQuery = ""
        searchResults = []
        isSearching = false
    }

    /// Get entities for a specific email
    func getEntities(for emailId: String) -> [ExtractedEntity] {
        Task {
            if await searchService.indexedEmailsCount == 0 {
                await searchService.indexEmails(emails)
            }
            return await searchService.getEntities(for: emailId)
        }
        return []
    }
}
