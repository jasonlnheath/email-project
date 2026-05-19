import SwiftUI

struct ContactsView: View {
    @StateObject private var viewModel = ContactsViewModel()
    @State private var searchText = ""

    var body: some View {
        NavigationView {
            VStack {
                if viewModel.isSyncing {
                    ProgressView("Syncing contacts...")
                        .padding()
                } else if let error = viewModel.errorMessage {
                    VStack(spacing: 16) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 40))
                            .foregroundColor(.orange)

                        Text("Error Loading Contacts")
                            .font(.headline)

                        Text(error)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)

                        Button("Retry") {
                            Task {
                                await viewModel.syncContacts()
                            }
                        }
                        .buttonStyle(.bordered)
                    }
                    .padding()
                } else if filteredContacts.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "person.2")
                            .font(.system(size: 40))
                            .foregroundColor(.secondary)

                        Text("No Contacts")
                            .font(.headline)

                        Text("Sign in with Google and sync your contacts to see them here.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)

                        if viewModel.lastSync == nil {
                            Button("Sync Contacts") {
                                Task {
                                    await viewModel.syncContacts()
                                }
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                    .padding()
                } else {
                    List(filteredContacts) { contact in
                        ContactRow(contact: contact)
                    }
                }
            }
            .navigationTitle("Contacts")
            .searchable(text: $searchText, prompt: "Search contacts")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        Task {
                            await viewModel.syncContacts()
                        }
                    } label: {
                        Label("Sync", systemImage: "arrow.clockwise")
                    }
                    .disabled(viewModel.isSyncing)
                }
            }
            .task {
                if viewModel.contacts.isEmpty && viewModel.lastSync == nil {
                    await viewModel.syncContacts()
                }
            }
        }
    }

    private var filteredContacts: [Contact] {
        viewModel.searchContacts(query: searchText)
    }
}

struct ContactRow: View {
    let contact: Contact

    var body: some View {
        HStack(spacing: 12) {
            // Contact photo or initials
            if let photoUrl = contact.photoUrl, let url = URL(string: photoUrl) {
                AsyncImage(url: url) { image in
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                } placeholder: {
                    contactInitials
                }
                .frame(width: 40, height: 40)
                .clipShape(Circle())
            } else {
                contactInitials
            }

            // Contact info
            VStack(alignment: .leading, spacing: 4) {
                if let name = contact.name {
                    Text(name)
                        .font(.headline)
                }

                Text(contact.email)
                    .font(.caption)
                    .foregroundColor(.secondary)

                if let phone = contact.phoneNumber {
                    Text(phone)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private var contactInitials: some View {
        ZStack {
            Circle()
                .fill(Color.blue.opacity(0.2))
                .frame(width: 40, height: 40)

            Text(initials)
                .font(.caption)
                .fontWeight(.semibold)
                .foregroundColor(.blue)
        }
    }

    private var initials: String {
        guard let name = contact.name else {
            return String(contact.email.prefix(2)).uppercased()
        }

        let components = name.components(separatedBy: .whitespaces).filter { !$0.isEmpty }
        let first = components.first.map { String($0.prefix(1)) } ?? ""
        let last = components.count > 1 ? components.last.map { String($0.prefix(1)) } ?? "" : ""
        return (first + last).uppercased()
    }
}

struct ContactsView_Previews: PreviewProvider {
    static var previews: some View {
        ContactsView()
    }
}
