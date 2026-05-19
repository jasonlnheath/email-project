import SwiftUI

struct SearchView: View {
    @EnvironmentObject var emailListVM: EmailListViewModel
    @EnvironmentObject var searchVM: SearchViewModel

    var body: some View {
        NavigationStack {
            List {
                if searchVM.results.isEmpty && !searchVM.searchText.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 40))
                            .foregroundStyle(.secondary)
                        Text("No Results")
                            .font(.title2)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 40)
                    .listRowBackground(Color.clear)
                } else {
                    ForEach(searchVM.results) { email in
                        NavigationLink {
                            EmailDetailView(email: email)
                        } label: {
                            EmailRow(email: email)
                        }
                    }
                }
            }
            .searchable(text: $searchVM.searchText, prompt: "Search emails...")
            .onChange(of: searchVM.searchText) { _ in
                searchVM.search(in: emailListVM.emails)
            }
            .navigationTitle("Search")
        }
    }
}

struct SearchView_Previews: PreviewProvider {
    static var previews: some View {
        SearchView()
            .environmentObject(EmailListViewModel())
            .environmentObject(SearchViewModel())
    }
}
