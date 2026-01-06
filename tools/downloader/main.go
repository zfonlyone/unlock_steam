/*
Steam Unlocker - 高并发下载器 (Go 版) v17
优化：
1. 【重要】实现 AppID 内部清单的二级并行：如果一个 Lua 脚本包含多个清单 ID，它们现在会并发下载，不再排队。
2. 增加下载重试机制 (3次随机退避)，大幅提高 GitHub 网络波动的容错率。
3. 优化进度统计，确保在二级并行下结果依然准确。
4. 延续 v16 的“原名保存”逻辑。
*/
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type Config struct {
	Token        string              `json:"token"`
	Repo         string              `json:"repo"`
	AppIDs       []string            `json:"app_ids"`
	AppData      map[string][]string `json:"app_data"`
	LuaDir       string              `json:"lua_dir"`
	ManifestDir  string              `json:"manifest_dir"`
	DirectMode   bool                `json:"direct_mode"`
	ManifestOnly bool                `json:"manifest_only"`
}

type AppResult struct {
	AppID    string `json:"app_id"`
	Lua      int    `json:"lua"`
	Manifest int    `json:"manifest"`
	Error    string `json:"error,omitempty"`
}

type Result struct {
	Success   bool        `json:"success"`
	Results   []AppResult `json:"results"`
	TotalTime float64     `json:"total_time_seconds"`
}

const (
	DOWNLOAD_CONCURRENCY = 100 // 主线程池：处理不同游戏的并发
	MAX_RETRIES          = 3   // 下载重试次数
)

var httpClient = &http.Client{
	Timeout: 60 * time.Second, // 略微增加超时
}

var (
	downloadedCount int64 = 0
	totalTaskCount  int64 = 0
	logMu           sync.Mutex
)

func main() {
	startTime := time.Now()

	configPath := flag.String("config", "", "JSON config file path")
	flag.Parse()

	var config Config
	if *configPath != "" {
		data, err := os.ReadFile(*configPath)
		if err != nil {
			outputError("无法读取配置文件: " + err.Error())
			return
		}
		if err := json.Unmarshal(data, &config); err != nil {
			outputError("配置文件 JSON 解析失败: " + err.Error())
			return
		}
	} else {
		decoder := json.NewDecoder(os.Stdin)
		if err := decoder.Decode(&config); err != nil {
			outputError("Stdin JSON 解析失败: " + err.Error())
			return
		}
	}

	if config.Repo == "" || len(config.AppIDs) == 0 {
		outputError("参数不足 (repo 或 app_ids 缺失)")
		return
	}

	if config.LuaDir != "" && !config.ManifestOnly {
		os.MkdirAll(config.LuaDir, 0755)
	}
	if config.ManifestDir != "" {
		os.MkdirAll(config.ManifestDir, 0755)
	}

	fmt.Printf("[INFO] downloader.exe version: 2026-01-06-v17 (Internal Parallel & Retry)\n")
	os.Stdout.Sync()

	results := processAllApps(config)

	output := Result{
		Success:   true,
		Results:   results,
		TotalTime: time.Since(startTime).Seconds(),
	}
	jsonOutput, _ := json.Marshal(output)
	fmt.Println(string(jsonOutput))
}

func downloadFileWithRetry(url, destPath, token string) error {
	var lastErr error
	for i := 0; i < MAX_RETRIES; i++ {
		err := downloadFile(url, destPath, token)
		if err == nil {
			return nil
		}
		lastErr = err
		// 如果是 404，不重试，直接换路径
		if strings.Contains(err.Error(), "Status 404") {
			return err
		}
		// 否则等待一小会重试
		time.Sleep(time.Duration(200*(i+1)) * time.Millisecond)
	}
	return lastErr
}

func downloadFile(url, destPath, token string) error {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return err
	}
	if token != "" {
		req.Header.Set("Authorization", "token "+token)
	}

	resp, err := httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return fmt.Errorf("Status %d", resp.StatusCode)
	}

	os.MkdirAll(filepath.Dir(destPath), 0755)
	out, err := os.Create(destPath)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, resp.Body)
	return err
}

func processAllApps(config Config) []AppResult {
	var results []AppResult
	taskChan := make(chan string, len(config.AppIDs))
	downloadResults := make(map[string]*AppResult)
	var downloadMu sync.Mutex
	var wg sync.WaitGroup

	atomic.StoreInt64(&totalTaskCount, int64(len(config.AppIDs)))

	for i := 0; i < DOWNLOAD_CONCURRENCY; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for appID := range taskChan {
				res := &AppResult{AppID: appID}

				// 1. 下载 Lua
				if !config.ManifestOnly && config.LuaDir != "" && config.DirectMode {
					for _, v := range []string{appID + ".lua", "depots.lua", "config.lua"} {
						url := fmt.Sprintf("https://raw.githubusercontent.com/%s/%s/%s", config.Repo, appID, v)
						if err := downloadFileWithRetry(url, filepath.Join(config.LuaDir, appID+".lua"), config.Token); err == nil {
							res.Lua = 1
							break
						}
					}
				}

				// 2. 下载清单 (二级并行)
				if mList, ok := config.AppData[appID]; ok && config.ManifestDir != "" && len(mList) > 0 {
					var mwg sync.WaitGroup
					var mCount int64 = 0

					for _, item := range mList {
						mwg.Add(1)
						go func(manifestItem string) {
							defer mwg.Done()
							parts := strings.Split(manifestItem, "_")
							var depotID, manifestID string
							if len(parts) == 2 {
								depotID, manifestID = parts[0], parts[1]
							} else {
								manifestID = manifestItem
							}

							var onlineNames []string
							if depotID != "" {
								onlineNames = append(onlineNames, fmt.Sprintf("%s_%s.manifest", depotID, manifestID), fmt.Sprintf("%s_%s", depotID, manifestID))
							}
							if appID != depotID {
								onlineNames = append(onlineNames, fmt.Sprintf("%s_%s.manifest", appID, manifestID), fmt.Sprintf("%s_%s", appID, manifestID))
							}
							onlineNames = append(onlineNames, manifestID+".manifest", manifestID)

							success := false
							for _, branch := range []string{appID, "main", "master"} {
								for _, oname := range onlineNames {
									url := fmt.Sprintf("https://raw.githubusercontent.com/%s/%s/%s", config.Repo, branch, oname)

									localName := oname
									if !strings.HasSuffix(localName, ".manifest") && !strings.Contains(localName, ".manifest") {
										localName += ".manifest"
									}
									destPath := filepath.Join(config.ManifestDir, localName)

									if err := downloadFileWithRetry(url, destPath, config.Token); err == nil {
										success = true
										atomic.AddInt64(&mCount, 1)
										logMu.Lock()
										// 内部日志减少刷屏，如需全量可开启
										// fmt.Printf("[DOWNLOAD_SUCCESS] %s -> %s\n", appID, localName)
										logMu.Unlock()
										break
									}
								}
								if success {
									break
								}
							}
						}(item)
					}
					mwg.Wait()
					res.Manifest = int(mCount)
				}

				downloadMu.Lock()
				downloadResults[appID] = res
				downloadMu.Unlock()

				count := atomic.AddInt64(&downloadedCount, 1)
				if count%100 == 0 || count == totalTaskCount {
					fmt.Printf("[PROGRESS] %d/%d\n", count, totalTaskCount)
					os.Stdout.Sync()
				}
			}
		}()
	}

	for _, id := range config.AppIDs {
		taskChan <- id
	}
	close(taskChan)
	wg.Wait()

	for _, id := range config.AppIDs {
		if r, ok := downloadResults[id]; ok {
			results = append(results, *r)
		}
	}
	return results
}

func outputError(msg string) {
	fmt.Printf("{\"success\":false,\"error\":\"%s\"}\n", msg)
}
