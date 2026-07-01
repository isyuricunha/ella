module.exports = {
  branches: ["main"],
  plugins: [
    [
      "@semantic-release/commit-analyzer",
      {
        preset: "angular",
        releaseRules: [
          { type: "refactor", release: "patch" },
          { type: "audit", release: "patch" }
        ]
      }
    ],
    [
      "@semantic-release/release-notes-generator",
      {
        preset: "angular",
        writerOpts: {
          transform: (commit, context) => {
            let discard = true;
            const issues = [];
            
            let type = commit.type;

            if (type === 'feat') {
              type = 'Features';
              discard = false;
            } else if (type === 'fix') {
              type = 'Bug Fixes';
              discard = false;
            } else if (type === 'perf') {
              type = 'Performance Improvements';
              discard = false;
            } else if (type === 'revert' || commit.revert) {
              type = 'Reverts';
              discard = false;
            } else if (type === 'refactor') {
              type = 'Code Refactoring';
              discard = false;
            } else if (type === 'audit') {
              type = 'Security Audits';
              discard = false;
            }

            if (discard) return undefined;

            let scope = commit.scope;
            if (scope === '*') {
              scope = '';
            }

            let shortHash = commit.shortHash;
            if (typeof commit.hash === 'string') {
              shortHash = commit.hash.substring(0, 7);
            }

            let subject = commit.subject;
            if (typeof subject === 'string') {
              let url = context.repository
                ? `${context.host}/${context.owner}/${context.repository}`
                : context.repoUrl;
              if (url) {
                url = `${url}/issues/`;
                subject = subject.replace(/#([0-9]+)/g, (_, issue) => {
                  issues.push(issue);
                  return `[#${issue}](${url}${issue})`;
                });
              }
              if (context.host) {
                subject = subject.replace(/\B@([a-z0-9](?:-?[a-z0-9/]){0,38})/g, (_, username) => {
                  if (username.includes('/')) {
                    return `@${username}`;
                  }
                  return `[@${username}](${context.host}/${username})`;
                });
              }
            }

            const references = (commit.references || []).filter(reference => {
              return issues.indexOf(reference.issue) === -1;
            });

            return {
              type,
              scope,
              shortHash,
              subject,
              references
            };
          }
        }
      }
    ],
    "@semantic-release/github"
  ]
};
