import SwiftUI

struct EmailListView: View {
    @EnvironmentObject var viewModel: EmailListViewModel
    @State private var showingFilterSheet = false
    @State private var showingSearch = false

    // Helper function to create a binding to the original email in the array
    private func bindingFor(email: EmailItem) -> Binding<EmailItem> {
        guard let index = viewModel.emails.firstIndex(where: { $0.emailId == email.emailId }) else {
            // Fallback to constant binding if email not found
            return .constant(email)
        }
        return $viewModel.emails[index]
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Search bar at top
                if showingSearch {
                    EmailSearchBar(
                        searchQuery: $viewModel.searchQuery,
                        searchScope: $viewModel.searchScope,
                        isSearching: $viewModel.isSearching,
                        onSearch: {
                            Task {
                                await viewModel.performSearch()
                            }
                        }
                    )
                    .transition(.move(edge: .top).combined(with: .opacity))
                }

                // Email list
                Group {
                    if viewModel.displayedEmails.isEmpty {
                        VStack(spacing: 12) {
                            Image(systemName: "envelope.badge")
                                .font(.system(size: 40))
                                .foregroundStyle(.secondary)
                            Text("No Emails")
                                .font(.title2)
                            if viewModel.emails.isEmpty {
                                Text("Tap the fetch button to load emails from Gmail")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                            } else if viewModel.isSearching {
                                Text("No emails match your search")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                Button("Clear Search") {
                                    viewModel.clearSearch()
                                }
                                .buttonStyle(.bordered)
                            } else {
                                Text("No emails match the current filters")
                                    .font(.subheadline)
                                    .foregroundStyle(.secondary)
                                Button("Clear Filters") {
                                    viewModel.clearFilters()
                                }
                                .buttonStyle(.bordered)
                            }
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        ScrollView {
                            LazyVStack(spacing: 12) {
                                ForEach(viewModel.displayedEmails.indices, id: \.self) { index in
                                    let email = viewModel.displayedEmails[index]
                                    ExpandableEmailRow(
                                        email: bindingFor(email: email),
                                        onSummarize: {
                                            viewModel.summarizeEmail(email)
                                        },
                                        onOpenGmail: {
                                            if let url = URL(string: email.gmailUrl) {
                                                UIApplication.shared.open(url)
                                                // Remove from list after opening
                                                viewModel.emails.removeAll { $0.emailId == email.emailId }
                                            }
                                        },
                                        onToggleRead: {
                                            viewModel.toggleRead(for: email)
                                        },
                                        onDelete: {
                                            viewModel.deleteEmail(email)
                                        },
                                        onUnsubscribe: {
                                            if email.unsubscribeUrl != nil {
                                                viewModel.unsubscribe(from: email)
                                            }
                                        }
                                    )
                                }
                            }
                            .padding()
                        }
                    }
                }
            }
            .navigationTitle("Emails")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    HStack {
                        // Search toggle button
                        Button {
                            withAnimation {
                                showingSearch.toggle()
                                if !showingSearch {
                                    viewModel.clearSearch()
                                }
                            }
                        } label: {
                            Image(systemName: "magnifyingglass")
                                .symbolRenderingMode(viewModel.isSearching ? .multicolor : .hierarchical)
                        }

                        Menu {
                            ForEach(SortOption.allCases, id: \.self) { option in
                                Button {
                                    viewModel.updateSortOption(option)
                                } label: {
                                    HStack {
                                        Text(option.displayName)
                                        if viewModel.currentSortOption == option {
                                            Image(systemName: "checkmark")
                                        }
                                    }
                                }
                            }
                        } label: {
                            Image(systemName: "arrow.up.arrow.down")
                        }
                    }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    HStack {
                        Button {
                            showingFilterSheet = true
                        } label: {
                            Image(systemName: "line.3.horizontal.decrease.circle")
                                .symbolRenderingMode(hasActiveFilters() ? .multicolor : .hierarchical)
                        }

                        Button(action: { viewModel.fetchEmails() }) {
                            if viewModel.isFetching {
                                ProgressView()
                            } else {
                                Label("Fetch", systemImage: "arrow.clockwise")
                            }
                        }
                        .disabled(viewModel.isFetching)
                    }
                }
            }
        }
        .sheet(isPresented: $showingFilterSheet) {
            FilterSheet(viewModel: viewModel)
        }
        .overlay(alignment: .bottom) {
            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage)
                    .foregroundStyle(.red)
                    .font(.caption)
                    .padding()
            }
        }
    }

    private func hasActiveFilters() -> Bool {
        viewModel.currentFilter.showUnreadOnly ||
        viewModel.currentFilter.showVIPOnly ||
        viewModel.currentFilter.showStarredOnly ||
        viewModel.currentFilter.priorityFilter != nil ||
        (viewModel.currentFilter.senderFilter?.isEmpty == false)
    }
}

struct EmailRow: View {
    let email: EmailItem

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(email.subject)
                .font(.headline)
                .lineLimit(1)
            HStack {
                Text(email.sender)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Spacer()
                Text(email.date, style: .date)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(email.snippet.isEmpty ? email.body : email.snippet)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .padding(.vertical, 2)
    }
}

struct EmailListView_Previews: PreviewProvider {
    static var previews: some View {
        EmailListView()
            .environmentObject(EmailListViewModel())
    }
}

/// Filter sheet for email filtering
struct FilterSheet: View {
    @ObservedObject var viewModel: EmailListViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var showUnreadOnly: Bool = false
    @State private var showVIPOnly: Bool = false
    @State private var showStarredOnly: Bool = false
    @State private var priorityFilter: EmailPriority? = nil
    @State private var senderFilter: String = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Status Filters") {
                    Toggle("Unread Only", isOn: $showUnreadOnly)
                    Toggle("VIP Only", isOn: $showVIPOnly)
                    Toggle("Starred Only", isOn: $showStarredOnly)
                }

                Section("Priority Filter") {
                    Picker("Priority", selection: $priorityFilter) {
                        Text("All").tag(nil as EmailPriority?)
                        ForEach(EmailPriority.allCases, id: \.self) { priority in
                            Text(priority.displayName).tag(priority as EmailPriority?)
                        }
                    }
                    .pickerStyle(.menu)
                }

                Section("Sender Filter") {
                    TextField("Filter by sender", text: $senderFilter)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                }

                Section {
                    Button("Clear All Filters") {
                        showUnreadOnly = false
                        showVIPOnly = false
                        showStarredOnly = false
                        priorityFilter = nil
                        senderFilter = ""
                    }
                    .foregroundColor(.red)
                }
            }
            .navigationTitle("Filter Emails")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Apply") {
                        applyFilters()
                        dismiss()
                    }
                }
            }
            .onAppear {
                // Load current filters
                showUnreadOnly = viewModel.currentFilter.showUnreadOnly
                showVIPOnly = viewModel.currentFilter.showVIPOnly
                showStarredOnly = viewModel.currentFilter.showStarredOnly
                priorityFilter = viewModel.currentFilter.priorityFilter
                senderFilter = viewModel.currentFilter.senderFilter ?? ""
            }
        }
    }

    private func applyFilters() {
        var filter = EmailFilter()
        filter.showUnreadOnly = showUnreadOnly
        filter.showVIPOnly = showVIPOnly
        filter.showStarredOnly = showStarredOnly
        filter.priorityFilter = priorityFilter
        filter.senderFilter = senderFilter.isEmpty ? nil : senderFilter
        viewModel.updateFilter(filter)
    }
}

/// Expandable email row component with priority border and inline actions
struct ExpandableEmailRow: View {
    @Binding var email: EmailItem
    var onSummarize: () -> Void
    var onOpenGmail: () -> Void
    var onToggleRead: () -> Void
    var onDelete: () -> Void
    var onUnsubscribe: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            // Full-height priority color strip
            Rectangle()
                .fill(EmailPriorityCalculator.color(for: email.priority))
                .frame(width: 6)

            VStack(alignment: .leading, spacing: 0) {
                // Header - tappable for expand/collapse
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(email.subject)
                            .font(.headline)
                            .lineLimit(2)
                        Spacer()
                        HStack(spacing: 4) {
                            Text(formattedDate(email.date))
                                .font(.caption2)
                                .foregroundColor(.secondary)
                            Image(systemName: email.isExpanded ? "chevron.down" : "chevron.right")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }

                    HStack {
                        Text(email.sender)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .lineLimit(1)

                        Spacer()

                        // VIP badge
                        if email.vipInfo != nil {
                            HStack(spacing: 2) {
                                Image(systemName: "star.fill")
                                    .font(.caption2)
                                    .foregroundColor(.yellow)
                            }
                        }

                        // Priority badge
                        Text(email.priority.displayName)
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(EmailPriorityCalculator.backgroundColor(for: email.priority))
                            .foregroundColor(EmailPriorityCalculator.color(for: email.priority))
                            .cornerRadius(3)
                    }
                }
                .padding(12)
                .contentShape(Rectangle())
                .onTapGesture {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        email.isExpanded.toggle()
                        // Auto-generate summary when expanding
                        if email.isExpanded && email.summary == nil {
                            onSummarize()
                        }
                    }
                }

                // Expanded section - shows summary
                if email.isExpanded {
                    Divider()

                    VStack(alignment: .leading, spacing: 8) {
                        if let summary = email.summary {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Summary")
                                    .font(.subheadline)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.secondary)
                                Text(summary)
                                    .font(.body)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                        } else {
                            HStack(spacing: 8) {
                                ProgressView()
                                    .scaleEffect(0.7)
                                Text("Generating summary...")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                        }
                    }
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }

                Divider()

                // Full-width action buttons
                VStack(spacing: 0) {
                    HStack(spacing: 0) {
                        DashboardActionButton(
                            title: email.isRead ? "Mark Unread" : "Mark Read",
                            icon: email.isRead ? "envelope.badge.fill" : "envelope.open.fill",
                            color: .blue,
                            action: onToggleRead
                        )

                        DashboardActionButton(
                            title: "Open",
                            icon: "arrow.up.right.square",
                            color: .green,
                            action: onOpenGmail
                        )

                        DashboardActionButton(
                            title: "Delete",
                            icon: "trash",
                            color: .red,
                            action: onDelete
                        )
                    }

                    if email.unsubscribeUrl != nil {
                        DashboardActionButton(
                            title: "Unsubscribe",
                            icon: "minus.circle",
                            color: .gray,
                            action: onUnsubscribe
                        )
                    }
                }
            }
        }
        .background(Color(.systemBackground))
        .cornerRadius(8)
        .shadow(color: Color.black.opacity(0.05), radius: 2, x: 0, y: 1)
    }

    private func formattedDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

// MARK: - Dashboard

/// ViewModel for Dashboard - shows unread emails sorted by priority
@MainActor
class DashboardViewModel: ObservableObject {
    @Published var emails: [EmailItem] = []
    @Published var isFetching = false
    @Published var errorMessage: String?
    @Published var isSignedIn = false
    @Published var totalUnreadCount: Int = 0
    @Published var selectedEmail: EmailItem?

    private let gmailService = GmailService()
    private let contactsService = ContactsService.shared
    private var vipContacts: [Contact] = []

    init() {
        Task {
            isSignedIn = await OAuthService.shared.isSignedIn
        }
    }

    /// Fetch only unread emails, sorted by priority
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

                // Fetch all emails from Gmail
                let gmailMessages = try await self.gmailService.fetchEmails(accessToken: accessToken)

                // Convert to EmailItem models
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
                        priority: .medium,
                        unsubscribeUrl: message.unsubscribeUrl
                    )

                    // Calculate priority
                    let priority = EmailPriorityCalculator.calculate(for: emailItem, vipContacts: contacts)
                    var updatedItem = emailItem
                    updatedItem.priority = priority

                    // Set VIP info if applicable
                    if let vip = contacts.first(where: { emailItem.sender.contains($0.email) }) {
                        updatedItem.vipInfo = VIPInfo(name: vip.name ?? "Unknown", relationshipType: "VIP")
                    }

                    return updatedItem
                }

                // Filter for unread emails, then sort by priority
                let filteredAndSorted = items
                    .filter { !$0.isRead }
                    .sorted { email1, email2 in
                        // Sort by priority first
                        let priorityOrder: [EmailPriority] = [.vipHigh, .high, .medium, .low]
                        let priority1Index = priorityOrder.firstIndex(of: email1.priority) ?? 3
                        let priority2Index = priorityOrder.firstIndex(of: email2.priority) ?? 3

                        if priority1Index != priority2Index {
                            return priority1Index < priority2Index
                        }

                        // Within same priority, sort by date (newest first)
                        return email1.date > email2.date
                    }

                await MainActor.run {
                    self.emails = filteredAndSorted
                    self.totalUnreadCount = filteredAndSorted.count
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

    /// Generate summary for selected email
    func generateSummary(for email: EmailItem) {
        Task {
            do {
                print("=== Generating summary for email: \(email.subject) ===")
                print("Body length: \(email.body.count)")
                print("Body preview: \(String(email.body.prefix(200)))")

                let llm = LLMProviderFactory.shared.getSelectedProvider()
                let result = try await llm.summarizeEmail(
                    subject: email.subject,
                    sender: email.sender,
                    body: String(email.body.prefix(3000))
                )

                print("Summary generated: \(result.summaryPurpose.prefix(100))...")
                print("Key entities: \(result.keyEntities)")
                print("Action items: \(result.actionItems)")

                await MainActor.run {
                    self.emails = self.emails.map { item in
                        if item.emailId == email.emailId {
                            var updated = item
                            updated.summary = result.summaryPurpose
                            return updated
                        }
                        return item
                    }

                    // Update selected email to show summary
                    if self.selectedEmail?.emailId == email.emailId {
                        var updatedSelected = email
                        updatedSelected.summary = result.summaryPurpose
                        self.selectedEmail = updatedSelected
                    }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to summarize: \(error.localizedDescription)"
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
                let gmailActionsService = GmailActionsService()

                if newReadState {
                    try await gmailActionsService.markAsRead(emailId: email.emailId, accessToken: accessToken)
                } else {
                    try await gmailActionsService.markAsUnread(emailId: email.emailId, accessToken: accessToken)
                }

                await MainActor.run {
                    // Update or remove from list based on new state
                    if newReadState {
                        // If marked as read, remove from dashboard
                        self.emails.removeAll { $0.emailId == email.emailId }
                        self.totalUnreadCount = max(0, self.totalUnreadCount - 1)
                    } else {
                        // Update the email
                        self.emails = self.emails.map { item in
                            if item.emailId == email.emailId {
                                var updated = item
                                updated.isRead = newReadState
                                return updated
                            }
                            return item
                        }
                    }

                    // Update selected email if it's the one we just modified
                    if self.selectedEmail?.emailId == email.emailId {
                        var updated = email
                        updated.isRead = newReadState
                        self.selectedEmail = updated
                    }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to update read status: \(error.localizedDescription)"
                }
            }
        }
    }

    func deleteEmail(_ email: EmailItem) {
        Task {
            do {
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                let gmailActionsService = GmailActionsService()

                try await gmailActionsService.deleteEmail(emailId: email.emailId, accessToken: accessToken)

                await MainActor.run {
                    self.emails.removeAll { $0.emailId == email.emailId }
                    self.totalUnreadCount = max(0, self.totalUnreadCount - 1)
                    self.selectedEmail = nil
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
                let gmailActionsService = GmailActionsService()

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
                let gmailActionsService = GmailActionsService()

                try await gmailActionsService.unsubscribe(emailId: email.emailId, unsubscribeUrl: unsubscribeUrl, accessToken: accessToken)

                await MainActor.run {
                    self.emails.removeAll { $0.emailId == email.emailId }
                    self.totalUnreadCount = max(0, self.totalUnreadCount - 1)
                    self.selectedEmail = nil
                    self.errorMessage = "Unsubscribed successfully"
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to unsubscribe: \(error.localizedDescription)"
                }
            }
        }
    }
}

/// Dashboard for quick processing of unread emails
struct DashboardView: View {
    @StateObject private var viewModel = DashboardViewModel()
    @State private var selectedEmailId: String?

    var body: some View {
        NavigationSplitView {
            // Email list
            Group {
                if viewModel.emails.isEmpty && !viewModel.isFetching {
                    emptyStateView
                } else {
                    emailListView
                }
            }
            .navigationTitle("Dashboard")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    if viewModel.totalUnreadCount > 0 {
                        HStack(spacing: 4) {
                            Circle()
                                .fill(Color.red)
                                .frame(width: 8, height: 8)
                            Text("\(viewModel.totalUnreadCount)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { viewModel.fetchEmails() }) {
                        if viewModel.isFetching {
                            ProgressView()
                        } else {
                            Label("Fetch", systemImage: "arrow.clockwise")
                        }
                    }
                    .disabled(viewModel.isFetching)
                }
            }
            .overlay(alignment: .bottom) {
                if let errorMessage = viewModel.errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                        .font(.caption)
                        .padding()
                        .background(Color(.systemBackground))
                        .cornerRadius(8)
                        .shadow(radius: 2)
                        .padding()
                }
            }
        } detail: {
            // Detail view (email opens to right)
            Group {
                if let emailId = selectedEmailId,
                   let email = viewModel.emails.first(where: { $0.emailId == emailId }) {
                    EmailDetailContentView(email: email)
                } else {
                    Text("Select an email to view")
                        .foregroundStyle(.secondary)
                        .navigationTitle("Email")
                }
            }
        }
        .onAppear {
            if viewModel.emails.isEmpty {
                viewModel.fetchEmails()
            }
        }
    }

    private var emptyStateView: some View {
        VStack(spacing: 12) {
            Image(systemName: "tray.full")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
            Text("All Caught Up!")
                .font(.title2)
            Text("No unread emails to process")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Button("Refresh") {
                viewModel.fetchEmails()
            }
            .buttonStyle(.bordered)
        }
    }

    private var emailListView: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(viewModel.emails.indices, id: \.self) { index in
                    DashboardEmailCard(
                        email: $viewModel.emails[index],
                        onToggleRead: {
                            viewModel.toggleRead(for: viewModel.emails[index])
                        },
                        onOpen: {
                            // Open directly in Gmail instead of detail view
                            if let url = URL(string: viewModel.emails[index].gmailUrl) {
                                UIApplication.shared.open(url)
                                // Remove from dashboard after opening
                                viewModel.emails.removeAll { $0.emailId == viewModel.emails[index].emailId }
                            }
                        },
                        onDelete: {
                            viewModel.deleteEmail(viewModel.emails[index])
                        },
                        onDefer: {
                            viewModel.deferEmail(viewModel.emails[index])
                        },
                        onUnsubscribe: {
                            if viewModel.emails[index].unsubscribeUrl != nil {
                                viewModel.unsubscribe(from: viewModel.emails[index])
                            }
                        },
                        onGenerateSummary: {
                            viewModel.generateSummary(for: viewModel.emails[index])
                        }
                    )
                }
            }
            .padding()
        }
    }
}

/// Compact email card for dashboard processing
struct DashboardEmailCard: View {
    @Binding var email: EmailItem
    var onToggleRead: () -> Void
    var onOpen: () -> Void
    var onDelete: () -> Void
    var onDefer: () -> Void
    var onUnsubscribe: () -> Void
    var onGenerateSummary: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            // Full-height priority color strip
            Rectangle()
                .fill(EmailPriorityCalculator.color(for: email.priority))
                .frame(width: 6)

            VStack(alignment: .leading, spacing: 0) {
                // Header - tappable for expand/collapse
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(email.subject)
                            .font(.headline)
                            .lineLimit(2)
                        Spacer()
                        HStack(spacing: 4) {
                            Text(formattedDate(email.date))
                                .font(.caption2)
                                .foregroundColor(.secondary)
                            Image(systemName: email.isExpanded ? "chevron.down" : "chevron.right")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }

                    HStack {
                        Text(email.sender)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .lineLimit(1)

                        Spacer()

                        // VIP badge
                        if email.vipInfo != nil {
                            HStack(spacing: 2) {
                                Image(systemName: "star.fill")
                                    .font(.caption2)
                                    .foregroundColor(.yellow)
                            }
                        }

                        // Priority badge
                        Text(email.priority.displayName)
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(EmailPriorityCalculator.backgroundColor(for: email.priority))
                            .foregroundColor(EmailPriorityCalculator.color(for: email.priority))
                            .cornerRadius(3)
                    }
                }
                .padding(12)
                .contentShape(Rectangle())
                .onTapGesture {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        email.isExpanded.toggle()
                        if email.isExpanded && email.summary == nil {
                            onGenerateSummary()
                        }
                    }
                }

                // Expanded section - shows only summary
                if email.isExpanded {
                    Divider()

                    VStack(alignment: .leading, spacing: 8) {
                        if let summary = email.summary {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Summary")
                                    .font(.subheadline)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.secondary)
                                Text(summary)
                                    .font(.body)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                        } else {
                            HStack(spacing: 8) {
                                ProgressView()
                                    .scaleEffect(0.7)
                                Text("Generating summary...")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                        }
                    }
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }

                Divider()

                // Full-width action buttons
                VStack(spacing: 0) {
                    HStack(spacing: 0) {
                        DashboardActionButton(
                            title: email.isRead ? "Mark Unread" : "Mark Read",
                            icon: email.isRead ? "envelope.badge.fill" : "envelope.open.fill",
                            color: .blue,
                            action: onToggleRead
                        )

                        DashboardActionButton(
                            title: "Open",
                            icon: "arrow.up.right.square",
                            color: .green,
                            action: onOpen
                        )

                        DashboardActionButton(
                            title: "Defer",
                            icon: "clock",
                            color: .orange,
                            action: onDefer
                        )

                        DashboardActionButton(
                            title: "Delete",
                            icon: "trash",
                            color: .red,
                            action: onDelete
                        )
                    }

                    if email.unsubscribeUrl != nil {
                        DashboardActionButton(
                            title: "Unsubscribe",
                            icon: "minus.circle",
                            color: .gray,
                            action: onUnsubscribe
                        )
                    }
                }
            }
        }
        .background(Color(.systemBackground))
        .cornerRadius(8)
        .shadow(color: Color.black.opacity(0.05), radius: 2, x: 0, y: 1)
    }

    private func formattedDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

/// Full-width action button for dashboard
struct DashboardActionButton: View {
    let title: String
    let icon: String
    let color: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.caption)
                Text(title)
                    .font(.caption)
                    .fontWeight(.medium)
            }
            .foregroundColor(color)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(color.opacity(0.12))
        }
        .buttonStyle(PlainButtonStyle())
    }
}

/// Inline email detail view (iOS Mail style)
struct EmailDetailContentView: View {
    let email: EmailItem

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Subject
                Text(email.subject)
                    .font(.title2)
                    .fontWeight(.bold)

                // Sender info
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(email.sender)
                            .font(.headline)
                        Text(formattedDate(email.date))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    Spacer()

                    if let vipInfo = email.vipInfo {
                        HStack(spacing: 4) {
                            Image(systemName: "star.fill")
                                .foregroundColor(.yellow)
                            Text(vipInfo.name)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }

                Divider()

                // Summary (if available)
                if let summary = email.summary {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Summary")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                        Text(summary)
                            .font(.body)
                    }
                    .padding()
                    .background(Color.purple.opacity(0.1))
                    .cornerRadius(8)
                }

                // Email body
                Text(email.body)
                    .font(.body)
            }
            .padding()
        }
        .navigationTitle("Email")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func formattedDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
}

// MARK: - Email Search Bar

/// Email search bar with scope selection
struct EmailSearchBar: View {
    @Binding var searchQuery: String
    @Binding var searchScope: SearchScope
    @Binding var isSearching: Bool
    let onSearch: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            // Search text field
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)

                TextField("Search emails...", text: $searchQuery)
                    .textFieldStyle(.plain)
                    .onSubmit {
                        onSearch()
                    }

                if !searchQuery.isEmpty {
                    Button {
                        searchQuery = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.secondary)
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(Color(.secondarySystemBackground))
            .cornerRadius(10)

            // Scope picker
            Picker("Scope", selection: $searchScope) {
                ForEach(SearchScope.allCases, id: \.self) { scope in
                    Text(scope.displayName).tag(scope)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 8)
        }
        .padding(.horizontal)
        .padding(.vertical, 12)
        .background(Color(.systemBackground))
        .overlay(
            Rectangle()
                .fill(Color(.separator).opacity(0.5))
                .frame(height: 0.5),
            alignment: .bottom
        )
    }
}
